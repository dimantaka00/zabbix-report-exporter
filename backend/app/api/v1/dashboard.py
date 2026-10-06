import asyncio
import os

from fastapi import APIRouter

from app.core.database import get_pool
from app.core.config import settings
from app.services.zabbix.client import ZabbixClient


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


REPORT_DIR = "/app/storage/reports"


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
        "scheduler": "running",
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
            import redis.asyncio as redis

            client = redis.from_url(
                redis_url,
                decode_responses=True,
            )

            await client.ping()
            await client.close()

            status["redis"] = "connected"

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