import asyncio
from pathlib import Path
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_pool
from app.models.requests import GenerateReportRequest
from app.services.report.data import collect_items
from app.services.report.downtime import collect_host_downtime
from app.services.report.pdf import REPORT_DIR, generate_multi_item_pdf
from app.services.zabbix.client import ZabbixClient
from app.services.report.archive import report_path

router = APIRouter(prefix="/reports", tags=["Reports"])
generation_limit = asyncio.Semaphore(2)


@router.get("")
async def list_reports(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    ready = set(await get_pool().fetchval("SELECT COALESCE(array_agg(archive_filename),ARRAY[]::text[]) FROM report_auto_runs WHERE archive_status='READY'"))
    rows = []
    for file in [*REPORT_DIR.glob("*.pdf"), *[p for p in REPORT_DIR.glob("*.zip") if p.name in ready]]:
        try:
            if file.is_symlink():
                continue
            stat = file.stat()
        except FileNotFoundError:
            continue
        rows.append({"filename": file.name, "size": stat.st_size, "created": stat.st_mtime,
                     "download_url": f"/api/v1/reports/{quote(file.name)}"})
    rows.sort(key=lambda row:row["created"],reverse=True)
    return {"success": True, "data": rows[offset:offset+limit], "total": len(rows)}


@router.post("/generate")
async def generate_report(payload: GenerateReportRequest):
    try:
        client = ZabbixClient(payload.zabbix_server)
        host = await client.validate_selection(payload.host_id, payload.host_name, payload.item_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, "Koneksi Zabbix belum tersedia.")
    pool = get_pool()
    execution_id = await pool.fetchval("""
        INSERT INTO report_execution_logs (schedule_name,host_name,trigger_type,status)
        VALUES ($1,$2,'manual_report','RUNNING') RETURNING id
    """, payload.title, host["name"] or host["host"])
    try:
        async with asyncio.timeout(settings.REPORT_TIMEOUT_SECONDS), generation_limit:
            data = await collect_items(client, payload.item_ids, payload.time_from, payload.time_till, payload.resolution)
            downtime = await collect_host_downtime(client, host["hostid"], payload.host_name,
                payload.time_from, payload.time_till, payload.downtime_trigger_id) if payload.include_downtime else None
            if not any(item["points"] for item in data) and not (downtime and downtime.get("events")):
                raise ValueError("Tidak ada data untuk periode laporan. Pilih metrik atau periode lain.")
            warnings = [f"{d['item']['name']}: {d['warning']}" for d in data if d.get("warning")]
            if downtime and downtime.get("warning"):
                warnings.append(f"Downtime: {downtime['warning']}")
            path = await run_in_threadpool(generate_multi_item_pdf, host["name"] or host["host"],
                data, payload.time_from, payload.time_till, payload.title, payload.timezone, downtime,
                chart_mode=payload.chart_mode)
        status = "PARTIAL" if warnings else "SUCCESS"
        await pool.execute("""
            UPDATE report_execution_logs SET finished_at=NOW(),status=$1,
                report_filename=$2,error_message=$3 WHERE id=$4
        """, status, path.name, "; ".join(warnings) or None, execution_id)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Pembuatan laporan gagal. Coba kembali atau periksa status layanan."
        await pool.execute("""
            UPDATE report_execution_logs SET finished_at=NOW(),status='FAILED',error_message=$1 WHERE id=$2
        """, message, execution_id)
        raise HTTPException(422 if isinstance(exc, ValueError) else 502, message)
    return FileResponse(str(path), media_type="application/pdf", filename=path.name,
                        headers={"X-Report-Status": status})


@router.get("/{filename}")
async def download_report(filename: str):
    path = (REPORT_DIR / filename).resolve()
    if path.parent != REPORT_DIR.resolve() or path.suffix.lower() not in (".pdf",".zip") or '\\' in filename or '/' in filename or (REPORT_DIR/filename).is_symlink():
        raise HTTPException(400, "Nama file tidak valid.")
    if not path.is_file():
        if path.suffix.lower() == ".pdf":
            archive = await get_pool().fetchval("""SELECT h.archive_filename FROM report_execution_logs h
                JOIN report_auto_runs r ON r.archive_filename=h.archive_filename AND r.archive_status='READY'
                WHERE h.report_filename=$1 LIMIT 1""",filename)
            if archive:
                return await download_member(archive,filename)
        raise HTTPException(404, "Laporan tidak ditemukan.")
    if path.suffix.lower() == ".zip" and not await get_pool().fetchval("SELECT EXISTS(SELECT 1 FROM report_auto_runs WHERE archive_filename=$1 AND archive_status='READY')",filename):
        raise HTTPException(404,"Arsip belum tersedia.")
    return FileResponse(str(path), media_type="application/zip" if path.suffix.lower()==".zip" else "application/pdf", filename=path.name)


@router.get("/archives/{archive_name}/{filename}")
async def download_member(archive_name: str, filename: str):
    try:
        path = report_path(archive_name,".zip")
        report_path(filename,".pdf")
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    registered = await get_pool().fetchval("""SELECT EXISTS(SELECT 1 FROM report_execution_logs h
        JOIN report_auto_runs r ON r.archive_filename=h.archive_filename AND r.archive_status='READY'
        WHERE h.archive_filename=$1 AND h.report_filename=$2)""",archive_name,filename)
    if not registered or not path.is_file():
        raise HTTPException(404,"PDF dalam ZIP tidak ditemukan.")
    try:
        with ZipFile(path) as archive:
            size = archive.getinfo(filename).file_size
    except (BadZipFile,KeyError,OSError):
        raise HTTPException(502,"Arsip PDF tidak dapat dibaca.")
    def stream():
        with ZipFile(path) as archive, archive.open(filename) as member:
            while chunk := member.read(128*1024):
                yield chunk
    return StreamingResponse(stream(),media_type="application/pdf",headers={
        "Content-Length":str(size),"Content-Disposition":f"attachment; filename*=UTF-8''{quote(filename)}"})
