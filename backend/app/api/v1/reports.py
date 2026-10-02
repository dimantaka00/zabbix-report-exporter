import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.report.pdf import (
    generate_multi_item_pdf,
)
from app.services.zabbix.client import (
    ZabbixClient,
)


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


REPORT_DIR = Path("/app/storage/reports")
REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


class GenerateReportRequest(BaseModel):
    host_name: str
    item_ids: list[str] = Field(
        min_length=1,
    )
    time_from: int
    time_till: int
    title: str = (
        "ZABBIX MONITORING REPORT"
    )


@router.get("")
async def list_reports():
    reports = []

    for file in sorted(
        REPORT_DIR.glob("*.pdf"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        stat = file.stat()

        reports.append(
            {
                "filename": file.name,
                "size": stat.st_size,
                "created": stat.st_mtime,
                "download_url": (
                    f"/api/v1/reports/{file.name}"
                ),
            }
        )

    return {
        "success": True,
        "data": reports,
    }


@router.post("/generate")
async def generate_report(
    payload: GenerateReportRequest,
):
    if payload.time_till <= payload.time_from:
        raise HTTPException(
            status_code=400,
            detail=(
                "time_till harus lebih besar "
                "dari time_from."
            ),
        )

    client = ZabbixClient()

    item_data_list = []

    for item_id in payload.item_ids:
        try:
            result = await client.get_item_data(
                itemid=str(item_id),
                time_from=payload.time_from,
                time_till=payload.time_till,
            )

            item_data_list.append(result)

        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Item {item_id} gagal "
                    f"diambil: {exc}"
                ),
            )

    try:
        pdf_path = generate_multi_item_pdf(
            host_name=payload.host_name,
            item_data_list=item_data_list,
            time_from=payload.time_from,
            time_till=payload.time_till,
            title=payload.title,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )


@router.get("/{filename}")
async def download_report(filename: str):
    file_path = (
        REPORT_DIR / filename
    ).resolve()

    if (
        file_path.parent
        != REPORT_DIR.resolve()
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    if (
        not file_path.exists()
        or not file_path.is_file()
    ):
        raise HTTPException(
            status_code=404,
            detail="Report not found.",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name,
    )