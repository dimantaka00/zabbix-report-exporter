import json
from fastapi import APIRouter, HTTPException

from app.core.database import decode_item_ids, get_pool
from app.models.requests import ScheduleCreate, ScheduleUpdate, ScheduleStatus
from app.services.scheduler.jobs import LOCK_NAMESPACE, run_schedule
from app.services.zabbix.client import ZabbixClient

router = APIRouter(prefix="/schedules", tags=["Schedules"])


def row_to_dict(row):
    result = dict(row)
    result["item_ids"] = decode_item_ids(result["item_ids"])
    for key in ("last_run_date", "created_at", "updated_at", "next_retry_at"):
        if result.get(key):
            result[key] = result[key].isoformat()
    return result


async def validate(payload):
    try:
        host = await ZabbixClient(payload.zabbix_server).validate_selection(
            payload.host_id, payload.host_name, payload.item_ids,
        )
        return host["hostid"], host["name"] or host["host"]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, "Validasi metrik Zabbix gagal. Periksa koneksi API.")


@router.get("")
async def list_schedules():
    rows = await get_pool().fetch("SELECT * FROM report_schedules ORDER BY created_at DESC")
    return {"success": True, "data": [row_to_dict(row) for row in rows]}


@router.post("")
async def create_schedule(payload: ScheduleCreate):
    host_id, host_name = await validate(payload)
    row = await get_pool().fetchrow("""
        INSERT INTO report_schedules
            (name, host_id, zabbix_server, host_name, item_ids, hour, minute, timezone, enabled)
        VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9) RETURNING *
    """, payload.name, host_id, payload.zabbix_server, host_name, json.dumps(payload.item_ids), payload.hour,
        payload.minute, payload.timezone, payload.enabled)
    return {"success": True, "data": row_to_dict(row)}


async def lock_schedule(conn, schedule_id):
    locked = await conn.fetchval(
        "SELECT pg_try_advisory_xact_lock($1::int,$2::int)", LOCK_NAMESPACE, schedule_id,
    )
    if not locked:
        raise HTTPException(409, "Jadwal sedang diproses. Tunggu sebelum mengubah atau menghapus.")
    row = await conn.fetchrow("SELECT * FROM report_schedules WHERE id=$1", schedule_id)
    if row is None:
        raise HTTPException(404, "Jadwal tidak ditemukan.")
    return row


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: int, payload: ScheduleUpdate):
    host_id, host_name = await validate(payload)
    async with get_pool().acquire() as conn, conn.transaction():
        await lock_schedule(conn, schedule_id)
        row = await conn.fetchrow("""
            UPDATE report_schedules SET name=$1,host_id=$2,zabbix_server=$3,host_name=$4,
                item_ids=$5::jsonb,hour=$6,minute=$7,timezone=$8,enabled=$9,
                next_retry_at=NULL,last_error=NULL,updated_at=NOW() WHERE id=$10 RETURNING *
        """, payload.name, host_id, payload.zabbix_server, host_name, json.dumps(payload.item_ids), payload.hour,
            payload.minute, payload.timezone, payload.enabled, schedule_id)
    return {"success": True, "data": row_to_dict(row)}


@router.patch("/{schedule_id}/status")
async def change_status(schedule_id: int, payload: ScheduleStatus):
    async with get_pool().acquire() as conn, conn.transaction():
        await lock_schedule(conn, schedule_id)
        row = await conn.fetchrow("""
            UPDATE report_schedules SET enabled=$1,next_retry_at=NULL,last_error=NULL,
                updated_at=NOW() WHERE id=$2 RETURNING *
        """, payload.enabled, schedule_id)
    return {"success": True, "data": row_to_dict(row)}


@router.post("/{schedule_id}/run")
async def run_now(schedule_id: int):
    row = await get_pool().fetchrow("SELECT * FROM report_schedules WHERE id=$1", schedule_id)
    if row is None:
        raise HTTPException(404, "Jadwal tidak ditemukan.")
    result = await run_schedule(row, force=True)
    return {"success": True, "data": result}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int):
    async with get_pool().acquire() as conn, conn.transaction():
        row = await lock_schedule(conn, schedule_id)
        await conn.execute("""
            UPDATE report_execution_logs SET schedule_name=COALESCE(schedule_name,$1),
                host_name=COALESCE(host_name,$2) WHERE schedule_id=$3
        """, row["name"], row["host_name"], schedule_id)
        await conn.execute("DELETE FROM report_schedules WHERE id=$1", schedule_id)
    return {"success": True}
