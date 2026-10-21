"""Build verified per-period ZIPs, then reclaim only their registered temporary PDFs."""
import hashlib
import json
import logging
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.database import get_pool

logger = logging.getLogger(__name__)
REPORT_DIR = settings.REPORT_STORAGE
ARCHIVE_LOCK = 710704
BACKUP_GUARD_LOCK = 710705


@asynccontextmanager
async def archive_connection():
    async with get_pool().acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock_shared($1,0)",BACKUP_GUARD_LOCK)
        try:
            yield conn if locked else None
        finally:
            if locked:
                await conn.fetchval("SELECT pg_advisory_unlock_shared($1,0)",BACKUP_GUARD_LOCK)


def report_path(filename, suffix):
    if not filename or '/' in filename or '\\' in filename or any(ord(c)<32 for c in filename):
        raise ValueError("Nama file tidak valid.")
    raw = Path(REPORT_DIR)/filename
    path = raw.resolve()
    if raw.is_symlink() or path.parent != Path(REPORT_DIR).resolve() or path.suffix.lower() != suffix:
        raise ValueError("Nama file tidak valid.")
    return path


def digest(stream):
    checksum = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024*1024), b''):
        checksum.update(chunk)
    return checksum.hexdigest()


def verify_archive(path):
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        files = manifest["files"]
        expected = [file["filename"] for file in files]+["manifest.json"]
        if len(expected) != len(set(expected)) or sorted(archive.namelist()) != sorted(expected):
            raise ValueError("Daftar file arsip tidak sesuai manifest.")
        for file in files:
            report_path(file["filename"], ".pdf")
            if archive.getinfo(file["filename"]).file_size != file["bytes"]:
                raise ValueError("Ukuran PDF pada arsip tidak cocok.")
            with archive.open(file["filename"]) as member:
                if digest(member) != file["sha256"]:
                    raise ValueError("Isi PDF pada arsip tidak cocok.")
    return manifest


def build_archive(filename, filenames, summary):
    output = report_path(filename, ".zip")
    files = []
    for name in filenames:
        source = report_path(name, ".pdf")
        with source.open("rb") as stream:
            files.append({"filename":name,"bytes":source.stat().st_size,"sha256":digest(stream)})
    manifest = {**summary,"files":files,"format_version":1}
    with tempfile.NamedTemporaryFile(dir=REPORT_DIR, prefix="archive_", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary,"w",compression=ZIP_DEFLATED,compresslevel=9,allowZip64=True) as archive:
            for file in files:
                archive.write(report_path(file["filename"],".pdf"),file["filename"])
            archive.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,default=str,indent=2))
        verify_archive(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output.stat().st_size, sum(file["bytes"] for file in files)


def cleanup_pdfs(filename, registered):
    # Reverification also protects restart recovery after READY was committed before cleanup.
    manifest = verify_archive(report_path(filename,".zip"))
    files = manifest["files"]
    if set(registered) != {file["filename"] for file in files}:
        raise ValueError("Daftar PDF terdaftar berbeda dengan isi ZIP. PDF asli dipertahankan.")
    paths = []
    for file in files:
        source = report_path(file["filename"],".pdf")
        if source.exists():
            with source.open("rb") as stream:
                if digest(stream) != file["sha256"]:
                    raise ValueError("PDF telah berubah. PDF asli dipertahankan.")
            paths.append(source)
    for source in paths:
        source.unlink(missing_ok=True)


async def archive_completed_runs():
    ids = await get_pool().fetch("""SELECT r.id FROM report_auto_runs r WHERE r.package_zip
        AND (r.archive_status IN ('PENDING','PACKING','ERROR') OR (r.archive_status='READY' AND NOT r.archive_cleanup_done))
        AND (r.archive_next_retry_at IS NULL OR r.archive_next_retry_at<=NOW())
        AND NOT EXISTS(SELECT 1 FROM report_auto_tasks t WHERE t.run_id=r.id AND t.status IN ('PENDING','RUNNING'))
        ORDER BY r.id LIMIT 10""")
    for row in ids:
        await archive_run(row["id"])


async def archive_run(run_id):
    async with archive_connection() as conn:
        if conn is None:
            return False
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1,$2)",ARCHIVE_LOCK,run_id):
            return False
        try:
            run = await conn.fetchrow("SELECT * FROM report_auto_runs WHERE id=$1",run_id)
            if not run or not run["package_zip"] or run["archive_status"] == "EMPTY" or (run["archive_status"] == "READY" and run["archive_cleanup_done"]):
                return False
            if await conn.fetchval("SELECT COUNT(*) FROM report_auto_tasks WHERE run_id=$1 AND status IN ('PENDING','RUNNING')",run_id):
                return False
            rows = await conn.fetch("""SELECT DISTINCT h.report_filename FROM report_execution_logs h
                JOIN report_auto_tasks t ON t.id=h.auto_task_id WHERE t.run_id=$1 AND h.report_filename IS NOT NULL
                AND h.status IN ('SUCCESS','PARTIAL') ORDER BY h.report_filename""",run_id)
            names = [row["report_filename"] for row in rows]
            if not names:
                await conn.execute("UPDATE report_auto_runs SET archive_status='EMPTY',archive_error='Tidak ada PDF berhasil dibuat.',archive_next_retry_at=NULL WHERE id=$1",run_id)
                return True
            filename = run["archive_filename"] or f"auto_report_{run['report_date']}_{run_id}_{uuid.uuid4().hex[:8]}.zip"
            try:
                if run["archive_status"] != "READY":
                    tasks = await conn.fetch("""SELECT host_name,zabbix_server,status,item_offset,files_completed,last_error
                        FROM report_auto_tasks WHERE run_id=$1 ORDER BY id""",run_id)
                    await conn.execute("UPDATE report_auto_runs SET archive_status='PACKING',archive_filename=$1,archive_error=NULL WHERE id=$2",filename,run_id)
                    summary = {"run_id":run_id,"schedule":run["schedule_name"],"report_date":str(run["report_date"]),
                               "timezone":run["timezone"],"data_start_time":run["data_start_time"],"data_end_time":run["data_end_time"],"hosts":[dict(task) for task in tasks]}
                    size, original = await run_in_threadpool(build_archive,filename,names,summary)
                    async with conn.transaction():
                        await conn.execute("""UPDATE report_auto_runs SET archive_status='READY',archive_size=$1,
                            original_size=$2,archive_error=NULL,archive_next_retry_at=NULL WHERE id=$3""",size,original,run_id)
                        await conn.execute("""UPDATE report_execution_logs h SET archive_filename=$1 FROM report_auto_tasks t
                            WHERE h.auto_task_id=t.id AND t.run_id=$2 AND h.report_filename=ANY($3::text[])
                            AND h.status IN ('SUCCESS','PARTIAL')""",filename,run_id,names)
                await run_in_threadpool(cleanup_pdfs,filename,names)
                await conn.execute("""UPDATE report_auto_runs SET archive_cleanup_done=TRUE,archive_error=NULL,
                    archive_next_retry_at=NULL WHERE id=$1""",run_id)
                return True
            except Exception:
                current = await conn.fetchval("SELECT archive_status FROM report_auto_runs WHERE id=$1",run_id)
                message = "Pengemasan atau pembersihan PDF belum selesai. PDF asli yang belum dibersihkan tetap disimpan; percobaan ulang dalam lima menit."
                await conn.execute("""UPDATE report_auto_runs SET archive_status=$1,archive_error=$2,
                    archive_next_retry_at=NOW()+INTERVAL '5 minutes' WHERE id=$3""",
                    "READY" if current == "READY" else "ERROR",message,run_id)
                logger.exception("Automatic archive %s failed",run_id)
                return False
        finally:
            await conn.fetchval("SELECT pg_advisory_unlock($1,$2)",ARCHIVE_LOCK,run_id)
