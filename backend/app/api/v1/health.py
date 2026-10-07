from fastapi import APIRouter, HTTPException
from app.core.database import get_pool

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health():
    return {"status": "ok", "service": "zabbix-report-exporter"}


@router.get("/ready")
async def readiness():
    try:
        await get_pool().fetchval("SELECT 1")
    except Exception:
        raise HTTPException(503, "Database belum tersedia.")
    return {"status": "ready", "service": "zabbix-report-exporter"}
