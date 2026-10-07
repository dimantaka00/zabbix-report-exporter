import os

from fastapi import APIRouter

from app.core.database import get_pool
from app.core.config import settings
from app.services.zabbix.client import ZabbixClient
from app.services.scheduler.heartbeat import HEARTBEAT_KEY, create_redis_client


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


REPORT_DIR = settings.REPORT_STORAGE


@router.get("/summary")
async def dashboard_summary():
    pool = get_pool()

    total_schedules = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM report_schedules;
        """
    )

    active_schedules = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM report_schedules
        WHERE enabled = TRUE;
        """
    )

    total_reports = 0

    if os.path.exists(REPORT_DIR):
        total_reports = len(
            [
                file
                for file in os.listdir(REPORT_DIR)
                if file.lower().endswith(".pdf")
            ]
        )

    return {
        "success": True,
        "data": {
            "total_schedules": total_schedules,
            "active_schedules": active_schedules,
            "total_reports": total_reports,
        },
    }


@router.get("/status")
async def dashboard_status():
    status = {
        "backend": "connected",
        "postgresql": "error",
        "redis": "error",
        "zabbix": "error",
        "scheduler": "unknown",
    }

    # PostgreSQL
    try:
        pool = get_pool()

        await pool.fetchval(
            "SELECT 1;"
        )

        status["postgresql"] = "connected"

    except Exception:
        status["postgresql"] = "error"

    # Redis
    try:
        redis_url = settings.REDIS_URL

        if redis_url:
            client = create_redis_client()
            try:
                await client.ping()
                worker_status = await client.get(HEARTBEAT_KEY)
                status["redis"] = "connected"
                if worker_status in ("starting", "running", "error"):
                    status["scheduler"] = worker_status
                elif worker_status is None:
                    status["scheduler"] = "stopped"
            finally:
                await client.aclose()

    except Exception:
        status["redis"] = "error"

    # Zabbix
    try:
        client = ZabbixClient()

        result = await client.get_hosts()

        if result is not None:
            status["zabbix"] = "connected"

    except Exception:
        status["zabbix"] = "error"

    return {
        "success": True,
        "data": status,
    }
