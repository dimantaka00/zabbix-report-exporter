import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import decode_item_ids, get_pool
from app.services.report.data import collect_items
from app.services.report.pdf import generate_multi_item_pdf
from app.services.zabbix.client import ZabbixClient

logger = logging.getLogger(__name__)
LOCK_NAMESPACE = 710700


async def run_schedule(schedule, force=False):
    pool = get_pool()
    async with pool.acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock($1::int, $2::int)", LOCK_NAMESPACE, schedule["id"])
        if not locked:
            if force:
                raise HTTPException(409, "Jadwal ini sedang diproses. Tunggu hingga selesai.")
            return None
        try:
            fresh = await conn.fetchrow("SELECT * FROM report_schedules WHERE id=$1", schedule["id"])
            if fresh is None:
                raise HTTPException(404, "Jadwal tidak ditemukan.")
            return await _execute(conn, fresh, force)
        finally:
            await conn.fetchval("SELECT pg_advisory_unlock($1::int, $2::int)", LOCK_NAMESPACE, schedule["id"])


async def _execute(conn, schedule, force):
    tz = ZoneInfo(schedule["timezone"])
    now = datetime.now(tz)
    today = now.date()
    scheduled = now.replace(hour=schedule["hour"], minute=schedule["minute"], second=0, microsecond=0)
    if not force:
        if not schedule["enabled"] or now < scheduled or schedule["last_run_date"] == today:
            return None
        if schedule["next_retry_at"] and now < schedule["next_retry_at"]:
            return False
    # An acquired session lock means no other process owns this schedule.
    await conn.execute("""
        UPDATE report_execution_logs SET status='FAILED', finished_at=NOW(),
            error_message='Eksekusi terputus sebelum selesai.'
        WHERE schedule_id=$1 AND status='RUNNING';
    """, schedule["id"])
    execution_id = await conn.fetchval("""
        INSERT INTO report_execution_logs (schedule_id, schedule_name, host_name, trigger_type, started_at, status)
        VALUES ($1, $2, $3, $4, $5, 'RUNNING') RETURNING id
    """, schedule["id"], schedule["name"], schedule["host_name"], "manual_schedule" if force else "scheduled", now)
    output = None
    try:
        day = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = int(day.timestamp()), int((day + timedelta(days=1)).timestamp()) - 1
        async with asyncio.timeout(settings.REPORT_TIMEOUT_SECONDS):
            data = await collect_items(ZabbixClient(), decode_item_ids(schedule["item_ids"]), start, end)
            if not any(d["points"] for d in data):
                raise ValueError("Tidak ada data untuk periode laporan. Periksa metrik atau pilih periode lain.")
            warnings = [f"{d['item']['name']}: {d['warning']}" for d in data if d.get("warning")]
            output = await run_in_threadpool(
                generate_multi_item_pdf, schedule["host_name"], data, start, end,
                schedule["name"], schedule["timezone"],
            )
        status = "PARTIAL" if warnings else "SUCCESS"
        warning = "; ".join(warnings) or None
        async with conn.transaction():
            await conn.execute("""
                UPDATE report_schedules SET last_run_date=$1, next_retry_at=NULL,
                    last_error=$2, updated_at=NOW() WHERE id=$3
            """, today, warning, schedule["id"])
            await conn.execute("""
                UPDATE report_execution_logs SET finished_at=NOW(), status=$1,
                    report_filename=$2, error_message=$3 WHERE id=$4
            """, status, output.name, warning, execution_id)
        logger.info("Schedule %s %s: %s", schedule["id"], status, output.name)
        return {"execution_id": execution_id, "status": status, "report_filename": output.name,
                "download_url": f"/api/v1/reports/{output.name}", "warning": warning}
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Pembuatan laporan gagal. Periksa koneksi Zabbix dan log layanan."
        logger.exception("Schedule %s failed", schedule["id"])
        async with conn.transaction():
            await conn.execute("""
                UPDATE report_schedules SET next_retry_at=NOW()+INTERVAL '5 minutes',
                    last_error=$1, updated_at=NOW() WHERE id=$2
            """, message, schedule["id"])
            await conn.execute("""
                UPDATE report_execution_logs SET finished_at=NOW(), status='FAILED',
                    error_message=$1 WHERE id=$2
            """, message, execution_id)
        if force:
            raise HTTPException(422, message)
        return False
