from fastapi import APIRouter, Query
from app.core.database import get_pool

router = APIRouter(prefix="/history", tags=["History"])


@router.get("")
async def get_execution_history(
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
):
    pool = get_pool()
    rows = await pool.fetch("""
        SELECT h.id,h.schedule_id,COALESCE(h.schedule_name,s.name) AS schedule_name,
            COALESCE(h.host_name,s.host_name) AS host_name,h.started_at,h.finished_at,
            h.status,h.report_filename,h.error_message,h.trigger_type
        FROM report_execution_logs h LEFT JOIN report_schedules s ON s.id=h.schedule_id
        ORDER BY h.started_at DESC,h.id DESC LIMIT $1 OFFSET $2
    """, limit, offset)
    total = await pool.fetchval("SELECT COUNT(*) FROM report_execution_logs")
    return {"success": True, "data": [dict(row) for row in rows], "total": total}
