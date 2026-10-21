"""Persistent daily all-host queue. Each host advances one bounded metric batch at a time."""
import asyncio
import json
import logging
import math
import re
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import decode_item_ids, get_pool
from app.services.report.data import collect_items
from app.services.report.downtime import collect_host_downtime
from app.services.report.pdf import generate_multi_item_pdf
from app.services.zabbix.client import ZabbixClient

logger = logging.getLogger(__name__)
POLICY_LOCK = 710701
TASK_LOCK = 710702
TERMINAL = ("SUCCESS", "PARTIAL", "FAILED", "SKIPPED")


def server_ids(selection):
    available = [server["id"] for server in ZabbixClient.configured_servers() if server["configured"]]
    if selection == "all":
        if not available:
            raise ValueError("Belum ada sumber Zabbix yang dikonfigurasi.")
        return available
    if selection not in available:
        raise ValueError("Sumber Zabbix belum dikonfigurasi.")
    return [selection]


def selected_hosts(hosts, status):
    wanted = {"enabled": "0", "disabled": "1"}.get(status)
    return [host for host in hosts if wanted is None or str(host.get("status")) == wanted]


def group_references(refs):
    return [{"zabbix_server":ref.split(":")[0],"group_id":ref.split(":")[1]} for ref in refs or []]


async def load_host_groups(selection):
    aliases = {"CS":("COMNET",),"TLK":("TLK","TELKOM"),"ICON":("ICON",),"HYP":("HYP","HYPERNET"),"MILES":("MILES",)}
    rows = []
    for source in server_ids(selection):
        for group in await ZabbixClient(source).get_host_groups():
            suggestions = [code for code,names in aliases.items() if any(re.search(r"(?<![A-Z0-9])"+name+r"(?![A-Z0-9])",group["name"],re.I) for name in names)]
            rows.append({"zabbix_server":source,"group_id":str(group["groupid"]),"name":group["name"],"suggested_categories":suggestions})
    return rows


async def inventory(selection, status, groups=None):
    result = []
    for source in server_ids(selection):
        ids = sorted({group["group_id"] for group in groups or [] if group["zabbix_server"] == source},key=int)
        if groups and not ids:
            continue
        hosts = await ZabbixClient(source).get_hosts(ids) if ids else await ZabbixClient(source).get_hosts()
        result.append((source, hosts, selected_hosts(hosts, status)))
    return result


def due_date(schedule, now=None):
    now = now or datetime.now(ZoneInfo(schedule["timezone"]))
    latest = now.date() if (now.hour, now.minute) >= (schedule["hour"], schedule["minute"]) else now.date()-timedelta(days=1)
    if schedule.get("date_end"):
        latest = min(latest,schedule["date_end"])
    previous = schedule["last_enqueued_date"]
    target = previous+timedelta(days=1) if previous else now.date()
    if schedule.get("date_start"):
        target = max(target,schedule["date_start"])
    return target if target <= latest else None


def report_period(day, timezone, start_time="00:00", end_time="23:59"):
    start = datetime.combine(day, time.fromisoformat(start_time), ZoneInfo(timezone))
    end = datetime.combine(day, time.fromisoformat(end_time), ZoneInfo(timezone)).replace(second=59)
    return int(start.timestamp()), int(end.timestamp())


async def enqueue_due_schedules():
    rows = await get_pool().fetch("SELECT * FROM report_auto_schedules WHERE enabled ORDER BY id")
    for row in rows:
        try:
            await enqueue_schedule(row["id"])
        except Exception:
            logger.exception("Automatic schedule enqueue failed: %s", row["id"])


async def enqueue_schedule(schedule_id):
    async with get_pool().acquire() as conn:
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1,$2)", POLICY_LOCK, schedule_id):
            return None
        try:
            schedule = await conn.fetchrow("SELECT * FROM report_auto_schedules WHERE id=$1", schedule_id)
            if not schedule or not schedule["enabled"]:
                return None
            now = datetime.now(ZoneInfo(schedule["timezone"]))
            day = due_date(schedule, now)
            if day is None or (schedule["next_retry_at"] and now < schedule["next_retry_at"]):
                return None
            try:
                backlog = await conn.fetchval("""SELECT COUNT(*) FROM report_auto_runs r
                    WHERE r.schedule_id=$1 AND EXISTS(SELECT 1 FROM report_auto_tasks t WHERE t.run_id=r.id
                    AND t.status IN ('PENDING','RUNNING'))""", schedule_id)
                if backlog >= settings.AUTO_MAX_PENDING_DAYS:
                    raise ValueError("Antrean mencapai tujuh periode. Tunggu pekerjaan sebelumnya selesai; periode berikutnya akan menyusul.")
                groups = decode_item_ids(schedule["host_groups"])
                if groups:
                    available = {(group["zabbix_server"],group["group_id"]) for group in await load_host_groups(schedule["zabbix_server"])}
                    if any((group["zabbix_server"],group["group_id"]) not in available for group in groups):
                        raise ValueError("Host group terpilih tidak tersedia. Perbarui pilihan group sebelum melanjutkan jadwal.")
                sources = await inventory(schedule["zabbix_server"], schedule["host_status"],groups) if groups else await inventory(schedule["zabbix_server"], schedule["host_status"])
                tasks = {(source, str(host["hostid"])): host for source, _, hosts in sources for host in hosts}
                selections = {(selected["zabbix_server"], selected["host_id"]): selected.get("item_ids")
                              for selected in decode_item_ids(schedule["host_selections"])}
                if schedule["selection_mode"] == "selected":
                    missing = set(selections)-set(tasks)
                    if missing:
                        raise ValueError("Sebagian host terpilih tidak tersedia atau tidak cocok dengan filter status. Perbarui pilihan host.")
                    tasks = {key: host for key, host in tasks.items() if key in selections}
                if not tasks:
                    raise ValueError("Tidak ada host yang cocok dengan sumber dan status terpilih.")
                async with conn.transaction():
                    # Recheck enabled while taking the policy row lock: pausing cannot race enqueue.
                    current = await conn.fetchrow("SELECT * FROM report_auto_schedules WHERE id=$1 FOR UPDATE", schedule_id)
                    if not current or not current["enabled"] or current["updated_at"] != schedule["updated_at"]:
                        return None
                    run_id = await conn.fetchval("""INSERT INTO report_auto_runs(schedule_id,schedule_name,timezone,execution_date,report_date,package_zip,archive_status,data_start_time,data_end_time)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(schedule_id,execution_date) DO NOTHING RETURNING id""",
                        schedule_id, schedule["name"], schedule["timezone"], day, day-timedelta(days=1), schedule["package_zip"],
                        "PENDING" if schedule["package_zip"] else "NONE",schedule["data_start_time"],schedule["data_end_time"])
                    if run_id:
                        await conn.executemany("""INSERT INTO report_auto_tasks(run_id,zabbix_server,host_id,host_name,selected_item_ids)
                            VALUES($1,$2,$3,$4,$5::jsonb)""", [(run_id, source, host_id, host.get("name") or host.get("host") or host_id,
                            json.dumps(selections[(source,host_id)]) if selections.get((source,host_id)) is not None else None)
                            for (source, host_id), host in tasks.items()])
                    await conn.execute("""UPDATE report_auto_schedules SET last_enqueued_date=$1,
                        next_retry_at=NULL,last_error=NULL WHERE id=$2""", day, schedule_id)
                return run_id
            except Exception as exc:
                message = str(exc) if isinstance(exc, ValueError) else "Inventaris Zabbix belum tersedia. Antrean akan dicoba lagi dalam lima menit."
                await conn.execute("""UPDATE report_auto_schedules SET last_error=$1,
                    next_retry_at=NOW()+INTERVAL '5 minutes' WHERE id=$2""", message, schedule_id)
                logger.warning("Automatic schedule %s: %s", schedule_id, message)
                return None
        finally:
            await conn.fetchval("SELECT pg_advisory_unlock($1,$2)", POLICY_LOCK, schedule_id)


async def process_one_task():
    async with get_pool().acquire() as conn:
        candidates = await conn.fetch("""SELECT t.id FROM report_auto_tasks t
            JOIN report_auto_runs r ON r.id=t.run_id JOIN report_auto_schedules s ON s.id=r.schedule_id
            WHERE s.enabled AND t.status IN ('PENDING','RUNNING')
            AND (t.next_retry_at IS NULL OR t.next_retry_at<=NOW()) ORDER BY r.report_date,t.id LIMIT 20""")
        for candidate in candidates:
            task_id = candidate["id"]
            if not await conn.fetchval("SELECT pg_try_advisory_lock($1,$2)", TASK_LOCK, task_id):
                continue
            try:
                task = await conn.fetchrow("""SELECT t.*,r.schedule_name,r.report_date,r.timezone,r.data_start_time,r.data_end_time FROM report_auto_tasks t
                    JOIN report_auto_runs r ON r.id=t.run_id JOIN report_auto_schedules s ON s.id=r.schedule_id
                    WHERE t.id=$1 AND s.enabled AND t.status IN ('PENDING','RUNNING')
                    AND (t.next_retry_at IS NULL OR t.next_retry_at<=NOW())""", task_id)
                if not task:
                    continue
                await conn.execute("UPDATE report_auto_tasks SET status='RUNNING',updated_at=NOW() WHERE id=$1", task_id)
                await conn.execute("""UPDATE report_execution_logs SET status='FAILED',finished_at=NOW(),
                    error_message='Eksekusi otomatis terputus; bagian ini dicoba kembali.'
                    WHERE auto_task_id=$1 AND status='RUNNING'""", task_id)
                await process_batch(conn, dict(task))
                return True
            finally:
                await conn.fetchval("SELECT pg_advisory_unlock($1,$2)", TASK_LOCK, task_id)
    return False


async def process_batch(conn, task):
    execution_id = None
    ids = None
    try:
        async with asyncio.timeout(settings.REPORT_TIMEOUT_SECONDS):
            client = ZabbixClient(task["zabbix_server"])
            selection_warning = task.get("selection_warning")
            ids = decode_item_ids(task["item_ids"]) if task["item_ids"] is not None else None
            if ids is None:
                items = await client.get_items(task["host_id"])
                ids = sorted({str(item["itemid"]) for item in items if str(item.get("value_type")) in ("0", "3")
                    and str(item.get("status")) == "0" and re.fullmatch(r"[0-9]{1,32}", str(item.get("itemid", "")))}, key=int)
                if task.get("selected_item_ids") is not None:
                    requested = set(decode_item_ids(task["selected_item_ids"]))
                    missing = requested-set(ids)
                    ids = [item_id for item_id in ids if item_id in requested]
                    if missing:
                        selection_warning = f"Metrik terpilih tidak tersedia atau tidak aktif: {', '.join(sorted(missing, key=int))}."
                        task["has_warnings"] = True
                await conn.execute("""UPDATE report_auto_tasks SET item_ids=$1::jsonb,selection_warning=$2,
                    has_warnings=has_warnings OR $3 WHERE id=$4""", json.dumps(ids), selection_warning, bool(selection_warning), task["id"])
            if not ids:
                await conn.execute("""UPDATE report_auto_tasks SET status=$1,last_error=$2,
                    updated_at=NOW(),next_retry_at=NULL WHERE id=$3""", "FAILED" if selection_warning else "SKIPPED",
                    selection_warning or "Tidak ada metrik numerik aktif.", task["id"])
                return
            offset = task["item_offset"]
            batch = ids[offset:offset+settings.MAX_REPORT_ITEMS]
            if not batch:
                await conn.execute("UPDATE report_auto_tasks SET status=$1 WHERE id=$2", final_status(task), task["id"])
                return
            number = offset//settings.MAX_REPORT_ITEMS+1
            count = math.ceil(len(ids)/settings.MAX_REPORT_ITEMS)
            title = f"{task['schedule_name']} · {task['zabbix_server']} · Bagian {number}/{count}"
            execution_id = await conn.fetchval("""INSERT INTO report_execution_logs(schedule_name,host_name,trigger_type,
                status,auto_task_id,auto_batch_index) VALUES($1,$2,'scheduled','RUNNING',$3,$4) RETURNING id""",
                title, task["host_name"], task["id"], number)
            start, end = report_period(task["report_date"], task["timezone"],task.get("data_start_time","00:00"),task.get("data_end_time","23:59"))
            data = await collect_items(client, batch, start, end, "minute")
            # Downtime is included once in the first part of each host's report.
            downtime = await collect_host_downtime(client, task["host_id"], task["host_name"], start, end) if offset == 0 else None
            warnings = [f"{metric['item']['name']}: {metric['warning']}" for metric in data if metric.get("warning")]
            if selection_warning and offset == 0:
                warnings.append(selection_warning)
            if downtime and downtime.get("warning"):
                warnings.append(f"Downtime: {downtime['warning']}")
            path = None
            if any(metric["points"] for metric in data) or (downtime and downtime.get("events")):
                path = await run_in_threadpool(generate_multi_item_pdf, task["host_name"], data, start, end,
                                               title, task["timezone"], downtime)
                report_status = "PARTIAL" if warnings else "SUCCESS"
            else:
                report_status = "FAILED"
                warnings.append(f"Tidak ada data pada bagian {number}/{count}; metrik: {', '.join(batch)}.")
            finished = offset+len(batch) >= len(ids)
            updated = {**task, "files_completed": task["files_completed"]+int(path is not None),
                "batches_failed": task["batches_failed"]+int(path is None),
                "has_warnings": task["has_warnings"] or bool(warnings)}
            async with conn.transaction():
                await conn.execute("""UPDATE report_execution_logs SET status=$1,finished_at=NOW(),
                    report_filename=$2,error_message=$3 WHERE id=$4""", report_status, path.name if path else None,
                    "; ".join(warnings)[:4000] or None, execution_id)
                await conn.execute("""UPDATE report_auto_tasks SET item_offset=$1,files_completed=$2,batches_failed=$3,
                    has_warnings=$4,status=$5,attempts=0,next_retry_at=NULL,last_error=$6,updated_at=NOW() WHERE id=$7""",
                    offset+len(batch), updated["files_completed"], updated["batches_failed"], updated["has_warnings"],
                    final_status(updated) if finished else "PENDING", "; ".join(warnings)[:4000] or None, task["id"])
    except Exception as exc:
        attempts = task["attempts"]+1
        message = str(exc) if isinstance(exc, ValueError) else "Bagian laporan gagal diproses. Periksa Zabbix atau log worker."
        async with conn.transaction():
            if execution_id:
                await conn.execute("""UPDATE report_execution_logs SET status='FAILED',finished_at=NOW(),error_message=$1
                    WHERE id=$2""", message, execution_id)
            if attempts >= settings.AUTO_MAX_ATTEMPTS and execution_id and ids:
                # A failed part must not prevent the remaining numeric metrics from being attempted.
                cursor = min(task["item_offset"]+settings.MAX_REPORT_ITEMS, len(ids))
                updated = {**task, "batches_failed": task["batches_failed"]+1, "has_warnings": True}
                await conn.execute("""UPDATE report_auto_tasks SET item_offset=$1,batches_failed=$2,
                    has_warnings=TRUE,status=$3,attempts=0,last_error=$4,next_retry_at=NULL,updated_at=NOW() WHERE id=$5""",
                    cursor, updated["batches_failed"], final_status(updated) if cursor >= len(ids) else "PENDING", message, task["id"])
            else:
                await conn.execute("""UPDATE report_auto_tasks SET status=$1,attempts=$2,last_error=$3,
                    next_retry_at=CASE WHEN $2::int >= $5::int THEN NULL ELSE NOW()+INTERVAL '5 minutes' END,
                    updated_at=NOW() WHERE id=$4""",
                    "FAILED" if attempts >= settings.AUTO_MAX_ATTEMPTS else "PENDING", attempts, message, task["id"], settings.AUTO_MAX_ATTEMPTS)
        logger.exception("Automatic host task failed: %s", task["id"])


def final_status(task):
    if task["files_completed"] == 0 and task["batches_failed"]:
        return "FAILED"
    return "PARTIAL" if task["has_warnings"] or task["batches_failed"] else "SUCCESS"


async def worker_loop():
    while True:
        try:
            worked = await process_one_task()
            await asyncio.sleep(0.1 if worked else 2)
        except Exception:
            logger.exception("Automatic queue worker failed")
            await asyncio.sleep(5)
