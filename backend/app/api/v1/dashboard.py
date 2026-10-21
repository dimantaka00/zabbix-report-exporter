import asyncio
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
STATUS_CHECK_TIMEOUT = 10


@router.get("/summary")
async def dashboard_summary():
    pool = get_pool()

    total_schedules = await pool.fetchval(
        """
        SELECT (SELECT COUNT(*) FROM report_schedules)
             + (SELECT COUNT(*) FROM report_auto_schedules);
        """
    )

    active_schedules = await pool.fetchval(
        """
        SELECT (SELECT COUNT(*) FROM report_schedules WHERE enabled=TRUE)
             + (SELECT COUNT(*) FROM report_auto_schedules WHERE enabled=TRUE);
        """
    )

    total_reports = 0

    if os.path.exists(REPORT_DIR):
        total_reports = len(
            [
                file
                for file in os.listdir(REPORT_DIR)
                if file.lower().endswith((".pdf", ".zip"))
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
        "zabbix_secondary": "not_configured",
        "scheduler": "unknown",
    }

    async def check_postgresql():
        try:
            await asyncio.wait_for(get_pool().fetchval("SELECT 1;"), STATUS_CHECK_TIMEOUT)
            status["postgresql"] = "connected"
        except Exception:
            status["postgresql"] = "error"

    async def redis_status():
        if settings.REDIS_URL:
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

    async def check_redis():
        try:
            await asyncio.wait_for(redis_status(), STATUS_CHECK_TIMEOUT)
        except Exception:
            status["redis"] = "error"
            status["scheduler"] = "unknown"

    async def check_zabbix(server):
        key = "zabbix" if server["id"] == "primary" else "zabbix_secondary"
        if not server["configured"]:
            status[key] = "not_configured"
            return
        try:
            connected = await asyncio.wait_for(
                ZabbixClient(server["id"]).check_connection(), STATUS_CHECK_TIMEOUT,
            )
            if connected:
                status[key] = "connected"
        except Exception:
            status[key] = "error"

    await asyncio.gather(
        check_postgresql(), check_redis(),
        *(check_zabbix(server) for server in ZabbixClient.configured_servers()),
    )

    return {
        "success": True,
        "data": status,
    }
