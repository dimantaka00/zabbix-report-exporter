import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.database import decode_item_ids, get_pool
from app.services.zabbix.client import ZabbixClient
from app.models.requests import AutoScheduleCreate, ScheduleStatus, GroupReference
from app.services.scheduler.auto import inventory, server_ids, group_references, load_host_groups

router = APIRouter(prefix="/auto-schedules", tags=["Automatic daily schedules"])


@router.get("/host-groups")
async def host_groups(zabbix_server: Literal["primary","secondary","all"] = Query("all")):
    try:
        rows = await load_host_groups(zabbix_server)
        return {"success":True,"data":rows}
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    except Exception:
        raise HTTPException(502,"Host group Zabbix tidak dapat dimuat. Periksa koneksi dan hak akses token.")


@router.get("/preview")
async def preview(zabbix_server: Literal["primary", "secondary", "all"] = Query("all"),
                  host_status: Literal["all", "enabled", "disabled"] = Query("all"),
                  group_refs: Annotated[list[GroupReference] | None, Query(max_length=200)] = None):
    try:
        groups = group_references(group_refs)
        if any(group["zabbix_server"] not in server_ids(zabbix_server) for group in groups):
            raise ValueError("Host group harus berasal dari sumber jadwal terpilih.")
        sources = await inventory(zabbix_server,host_status,groups) if groups else await inventory(zabbix_server, host_status)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(502, "Inventaris Zabbix tidak dapat dimuat. Periksa koneksi sumber terpilih.")
    return {"success": True, "data": {"hosts": sum(len(hosts) for _, _, hosts in sources),
        "servers": [{"id": source, "hosts": len(selected), "enabled": sum(str(h.get('status')) == '0' for h in selected),
                     "disabled": sum(str(h.get('status')) == '1' for h in selected)} for source, _, selected in sources],
        "metric_selection": "all_numeric", "max_metrics_per_pdf": settings.MAX_REPORT_ITEMS}}


@router.get("")
async def list_schedules():
    rows = await get_pool().fetch("""SELECT s.*,r.id AS run_id,r.report_date,r.execution_date,
        r.archive_filename,r.archive_status,r.archive_size,r.original_size,r.archive_error,
        COALESCE(p.total,0) AS total_hosts,COALESCE(p.done,0) AS done_hosts,
        COALESCE(p.success,0) AS successful_hosts,COALESCE(p.partial,0) AS partial_hosts,
        COALESCE(p.failed,0) AS failed_hosts,COALESCE(p.skipped,0) AS skipped_hosts,
        COALESCE(p.running,0) AS running_hosts,COALESCE(p.files,0) AS files_completed,
        COALESCE(p.metrics,0) AS total_metrics,COALESCE(p.processed,0) AS processed_metrics,
        (SELECT COUNT(*) FROM report_auto_runs backlog WHERE backlog.schedule_id=s.id AND EXISTS(
            SELECT 1 FROM report_auto_tasks remaining WHERE remaining.run_id=backlog.id AND remaining.status IN ('PENDING','RUNNING'))) AS pending_periods
        FROM report_auto_schedules s
        LEFT JOIN LATERAL(SELECT * FROM report_auto_runs WHERE schedule_id=s.id ORDER BY execution_date DESC LIMIT 1) r ON TRUE
        LEFT JOIN LATERAL(SELECT COUNT(*) AS total,COUNT(*) FILTER(WHERE status IN ('SUCCESS','PARTIAL','FAILED','SKIPPED')) AS done,
            COUNT(*) FILTER(WHERE status='SUCCESS') AS success,COUNT(*) FILTER(WHERE status='PARTIAL') AS partial,
            COUNT(*) FILTER(WHERE status='FAILED') AS failed,COUNT(*) FILTER(WHERE status='SKIPPED') AS skipped,
            COUNT(*) FILTER(WHERE status='RUNNING') AS running,SUM(files_completed) AS files,
            SUM(COALESCE(jsonb_array_length(item_ids),0)) AS metrics,SUM(item_offset) AS processed
            FROM report_auto_tasks WHERE run_id=r.id) p ON TRUE ORDER BY s.id DESC""")
    result = []
    for row in rows:
        item = dict(row)
        item["host_selections"] = decode_item_ids(item["host_selections"])
        item["host_categories"] = decode_item_ids(item["host_categories"])
        item["host_groups"] = decode_item_ids(item["host_groups"])
        today = datetime.now(ZoneInfo(item["timezone"])).date()
        item["date_status"] = "UPCOMING" if item["date_start"] and today < item["date_start"] else (
            "EXPIRED" if item["date_end"] and today > item["date_end"] else "ACTIVE")
        item["archive_download_url"] = f"/api/v1/reports/{quote(item['archive_filename'])}" if item["archive_status"] == "READY" else None
        if not item["run_id"]:
            state = "WAITING"
        elif item["done_hosts"] == item["total_hosts"] and not item["pending_periods"]:
            state = "FAILED" if item["failed_hosts"] and not item["files_completed"] else (
                "PARTIAL" if item["failed_hosts"] or item["partial_hosts"] else "COMPLETED")
        elif not item["enabled"]:
            state = "PAUSED"
        else:
            state = "RUNNING" if item["running_hosts"] or item["done_hosts"] or item["processed_metrics"] else "QUEUED"
        item["run_status"] = state
        result.append(item)
    return {"success": True, "data": result}


async def check_limit(conn, enabled, exclude_id=0):
    if enabled and await conn.fetchval("SELECT COUNT(*) FROM report_auto_schedules WHERE enabled AND id<>$1", exclude_id) >= settings.AUTO_MAX_ACTIVE_SCHEDULES:
        raise HTTPException(400, "Maksimal sepuluh jadwal otomatis aktif. Nonaktifkan jadwal lain terlebih dahulu.")


async def validate(payload):
    try:
        sources = server_ids(payload.zabbix_server)
        if any(host.zabbix_server not in sources for host in payload.host_selections):
            raise ValueError("Sumber host terpilih belum dikonfigurasi.")
        groups = [group.model_dump() for group in payload.host_groups]
        if any(group["zabbix_server"] not in sources for group in groups):
            raise ValueError("Sumber host group belum dikonfigurasi.")
        if groups:
            catalog = {(group["zabbix_server"],group["group_id"]):group for group in await load_host_groups(payload.zabbix_server)}
            if any((group["zabbix_server"],group["group_id"]) not in catalog for group in groups):
                raise ValueError("Host group terpilih tidak ditemukan atau tidak dapat diakses.")
            if any(group["category"] not in catalog[(group["zabbix_server"],group["group_id"])]["suggested_categories"] for group in groups):
                raise ValueError("Host group tidak cocok dengan kategori terpilih. Kategori CS memakai group COMNET saja.")
        if payload.selection_mode == "selected":
            async with asyncio.timeout(60):
                found = await inventory(payload.zabbix_server,payload.host_status,groups) if groups else await inventory(payload.zabbix_server,payload.host_status)
                hosts = {(source,str(host["hostid"])) for source, _, selected in found for host in selected}
                if any((host.zabbix_server,host.host_id) not in hosts for host in payload.host_selections):
                    raise ValueError("Host terpilih tidak tersedia atau tidak cocok dengan filter status.")
                semaphore = asyncio.Semaphore(4)
                async def check(selected):
                    if selected.item_ids is None:
                        return
                    async with semaphore:
                        items = await ZabbixClient(selected.zabbix_server).get_items(selected.host_id)
                        valid = {str(item["itemid"]) for item in items if str(item.get("value_type")) in ("0","3") and str(item.get("status")) == "0"}
                        if not set(selected.item_ids) <= valid:
                            raise ValueError("Pilih metrik numerik aktif dari host yang dipilih.")
                await asyncio.gather(*(check(selected) for selected in payload.host_selections))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Pilihan host/metrik tidak dapat diperiksa. Periksa koneksi Zabbix lalu coba kembali.")


def serialize(row):
    item = dict(row)
    item["host_selections"] = decode_item_ids(item["host_selections"])
    item["host_categories"] = decode_item_ids(item["host_categories"])
    item["host_groups"] = decode_item_ids(item["host_groups"])
    return item


@router.post("")
async def create(payload: AutoScheduleCreate):
    await validate(payload)
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(710703)")
        await check_limit(conn, payload.enabled)
        row = await conn.fetchrow("""INSERT INTO report_auto_schedules(name,zabbix_server,host_status,hour,minute,timezone,enabled,selection_mode,host_selections,package_zip,
            data_start_time,data_end_time,date_start,date_end,host_categories,host_groups)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,$15::jsonb,$16::jsonb) RETURNING *""", payload.name, payload.zabbix_server, payload.host_status,
            payload.hour, payload.minute, payload.timezone, payload.enabled, payload.selection_mode,
            json.dumps([host.model_dump() for host in payload.host_selections]), payload.package_zip,
            payload.data_start_time,payload.data_end_time,payload.date_start,payload.date_end,
            json.dumps(payload.host_categories),json.dumps([group.model_dump() for group in payload.host_groups]))
    return {"success": True, "data": serialize(row)}


@router.put("/{schedule_id}")
async def update(schedule_id: int, payload: AutoScheduleCreate):
    await validate(payload)
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(710703)")
        await check_limit(conn, payload.enabled, schedule_id)
        row = await conn.fetchrow("""UPDATE report_auto_schedules SET name=$1,zabbix_server=$2,host_status=$3,
            hour=$4,minute=$5,timezone=$6,enabled=$7,next_retry_at=NULL,last_error=NULL,updated_at=NOW()
            ,selection_mode=$8,host_selections=$9::jsonb,package_zip=$10,data_start_time=$11,data_end_time=$12,
            date_start=$13,date_end=$14,host_categories=$15::jsonb,host_groups=$16::jsonb WHERE id=$17 RETURNING *""", payload.name, payload.zabbix_server, payload.host_status,
            payload.hour, payload.minute, payload.timezone, payload.enabled, payload.selection_mode,
            json.dumps([host.model_dump() for host in payload.host_selections]), payload.package_zip,
            payload.data_start_time,payload.data_end_time,payload.date_start,payload.date_end,
            json.dumps(payload.host_categories),json.dumps([group.model_dump() for group in payload.host_groups]), schedule_id)
        if not row:
            raise HTTPException(404, "Jadwal otomatis tidak ditemukan.")
    return {"success": True, "data": serialize(row)}


@router.patch("/{schedule_id}/status")
async def status(schedule_id: int, payload: ScheduleStatus):
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(710703)")
        await check_limit(conn, payload.enabled, schedule_id)
        row = await conn.fetchrow("""UPDATE report_auto_schedules SET enabled=$1,next_retry_at=NULL,last_error=NULL,
            updated_at=NOW() WHERE id=$2 RETURNING *""", payload.enabled, schedule_id)
        if not row:
            raise HTTPException(404, "Jadwal otomatis tidak ditemukan.")
    return {"success": True, "data": serialize(row)}


@router.delete("/{schedule_id}")
async def delete(schedule_id: int):
    deleted = await get_pool().fetchval("DELETE FROM report_auto_schedules WHERE id=$1 RETURNING id", schedule_id)
    if not deleted:
        raise HTTPException(404, "Jadwal otomatis tidak ditemukan.")
    return {"success": True}


@router.get("/{schedule_id}/tasks")
async def tasks(schedule_id: int, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    run_id = await get_pool().fetchval("SELECT id FROM report_auto_runs WHERE schedule_id=$1 ORDER BY execution_date DESC LIMIT 1", schedule_id)
    if run_id is None:
        return {"success": True, "data": [], "total": 0}
    rows = await get_pool().fetch("""SELECT id,host_name,zabbix_server,status,item_offset,
        COALESCE(jsonb_array_length(item_ids),0) AS total_metrics,files_completed,last_error,next_retry_at
        FROM report_auto_tasks WHERE run_id=$1 ORDER BY id LIMIT $2 OFFSET $3""", run_id, limit, offset)
    total = await get_pool().fetchval("SELECT COUNT(*) FROM report_auto_tasks WHERE run_id=$1", run_id)
    return {"success": True, "data": [dict(row) for row in rows], "total": total}
