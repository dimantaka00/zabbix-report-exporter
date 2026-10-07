import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_pool
from app.models.requests import GenerateReportRequest
from app.services.report.data import collect_items
from app.services.report.pdf import REPORT_DIR, generate_multi_item_pdf
from app.services.zabbix.client import ZabbixClient

router = APIRouter(prefix="/reports", tags=["Reports"])
generation_limit = asyncio.Semaphore(2)


@router.get("")
async def list_reports(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    files = sorted(REPORT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for file in files[offset:offset + limit]:
        stat = file.stat()
        rows.append({"filename": file.name, "size": stat.st_size, "created": stat.st_mtime,
                     "download_url": f"/api/v1/reports/{file.name}"})
    return {"success": True, "data": rows, "total": len(files)}


@router.post("/generate")
async def generate_report(payload: GenerateReportRequest):
    try:
        client = ZabbixClient()
        host = await client.validate_selection(payload.host_id, payload.host_name, payload.item_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(502, "Koneksi Zabbix belum tersedia.")
    pool = get_pool()
    execution_id = await pool.fetchval("""
        INSERT INTO report_execution_logs (schedule_name,host_name,trigger_type,status)
        VALUES ($1,$2,'manual_report','RUNNING') RETURNING id
    """, payload.title, host["name"] or host["host"])
    try:
        async with asyncio.timeout(settings.REPORT_TIMEOUT_SECONDS), generation_limit:
            data = await collect_items(client, payload.item_ids, payload.time_from, payload.time_till)
            if not any(item["points"] for item in data):
                raise ValueError("Tidak ada data untuk periode laporan. Pilih metrik atau periode lain.")
            warnings = [f"{d['item']['name']}: {d['warning']}" for d in data if d.get("warning")]
            path = await run_in_threadpool(generate_multi_item_pdf, host["name"] or host["host"],
                data, payload.time_from, payload.time_till, payload.title, payload.timezone)
        status = "PARTIAL" if warnings else "SUCCESS"
        await pool.execute("""
            UPDATE report_execution_logs SET finished_at=NOW(),status=$1,
                report_filename=$2,error_message=$3 WHERE id=$4
        """, status, path.name, "; ".join(warnings) or None, execution_id)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Pembuatan laporan gagal. Coba kembali atau periksa status layanan."
        await pool.execute("""
            UPDATE report_execution_logs SET finished_at=NOW(),status='FAILED',error_message=$1 WHERE id=$2
        """, message, execution_id)
        raise HTTPException(422 if isinstance(exc, ValueError) else 502, message)
    return FileResponse(str(path), media_type="application/pdf", filename=path.name,
                        headers={"X-Report-Status": status})


@router.get("/{filename}")
async def download_report(filename: str):
    path = (REPORT_DIR / filename).resolve()
    if path.parent != REPORT_DIR.resolve() or path.suffix.lower() != ".pdf":
        raise HTTPException(400, "Nama file tidak valid.")
    if not path.is_file():
        raise HTTPException(404, "Laporan tidak ditemukan.")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)
