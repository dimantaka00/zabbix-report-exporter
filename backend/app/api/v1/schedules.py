import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.database import (
    decode_item_ids,
    get_pool,
)


router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"],
)


class ScheduleCreate(BaseModel):
    name: str
    host_id: str | None = None
    host_name: str
    item_ids: list[str] = Field(
        default_factory=list,
    )
    hour: int = Field(
        default=7,
        ge=0,
        le=23,
    )
    minute: int = Field(
        default=0,
        ge=0,
        le=59,
    )
    timezone: str = "Asia/Jakarta"
    enabled: bool = True


class ScheduleUpdate(ScheduleCreate):
    pass


def row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "host_id": row["host_id"],
        "host_name": row["host_name"],
        "item_ids": decode_item_ids(
            row["item_ids"]
        ),
        "hour": row["hour"],
        "minute": row["minute"],
        "timezone": row["timezone"],
        "enabled": row["enabled"],
        "last_run_date": (
            row["last_run_date"].isoformat()
            if row["last_run_date"]
            else None
        ),
        "created_at": row[
            "created_at"
        ].isoformat(),
        "updated_at": row[
            "updated_at"
        ].isoformat(),
    }


@router.get("")
async def list_schedules():
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT
            id,
            name,
            host_id,
            host_name,
            item_ids,
            hour,
            minute,
            timezone,
            enabled,
            last_run_date,
            created_at,
            updated_at
        FROM report_schedules
        ORDER BY created_at DESC;
        """
    )

    return {
        "success": True,
        "data": [
            row_to_dict(row)
            for row in rows
        ],
    }


@router.post("")
async def create_schedule(
    payload: ScheduleCreate,
):
    pool = get_pool()

    row = await pool.fetchrow(
        """
        INSERT INTO report_schedules (
            name,
            host_id,
            host_name,
            item_ids,
            hour,
            minute,
            timezone,
            enabled
        )
        VALUES (
            $1,
            $2,
            $3,
            $4::jsonb,
            $5,
            $6,
            $7,
            $8
        )
        RETURNING
            id,
            name,
            host_id,
            host_name,
            item_ids,
            hour,
            minute,
            timezone,
            enabled,
            last_run_date,
            created_at,
            updated_at;
        """,
        payload.name,
        payload.host_id,
        payload.host_name,
        json.dumps(payload.item_ids),
        payload.hour,
        payload.minute,
        payload.timezone,
        payload.enabled,
    )

    return {
        "success": True,
        "data": row_to_dict(row),
    }


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
):
    pool = get_pool()

    row = await pool.fetchrow(
        """
        UPDATE report_schedules
        SET
            name = $1,
            host_id = $2,
            host_name = $3,
            item_ids = $4::jsonb,
            hour = $5,
            minute = $6,
            timezone = $7,
            enabled = $8,
            updated_at = NOW()
        WHERE id = $9
        RETURNING
            id,
            name,
            host_id,
            host_name,
            item_ids,
            hour,
            minute,
            timezone,
            enabled,
            last_run_date,
            created_at,
            updated_at;
        """,
        payload.name,
        payload.host_id,
        payload.host_name,
        json.dumps(payload.item_ids),
        payload.hour,
        payload.minute,
        payload.timezone,
        payload.enabled,
        schedule_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Schedule tidak ditemukan.",
        )

    return {
        "success": True,
        "data": row_to_dict(row),
    }


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
):
    pool = get_pool()

    result = await pool.execute(
        """
        DELETE FROM report_schedules
        WHERE id = $1;
        """,
        schedule_id,
    )

    if result == "DELETE 0":
        raise HTTPException(
            status_code=404,
            detail="Schedule tidak ditemukan.",
        )

    return {
        "success": True,
    }