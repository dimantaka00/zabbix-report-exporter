from fastapi import APIRouter

from app.core.database import get_pool


router = APIRouter(
    prefix="/history",
    tags=["History"],
)


@router.get("")
async def get_execution_history():
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT
            h.id,
            h.schedule_id,
            s.name AS schedule_name,
            s.host_name,
            h.started_at,
            h.finished_at,
            h.status,
            h.report_filename,
            h.error_message
        FROM report_execution_logs h
        LEFT JOIN report_schedules s
            ON s.id = h.schedule_id
        ORDER BY h.started_at DESC
        LIMIT 100;
        """
    )

    return {
        "success": True,
        "data": [
            dict(row)
            for row in rows
        ],
    }