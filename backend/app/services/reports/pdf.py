"""Compatibility wrapper around the shared PDF generator."""

from pathlib import Path

from app.services.report.pdf import REPORT_DIR, generate_multi_item_pdf


def generate_pdf(
    host_name: str,
    item_name: str,
    units: str,
    source: str,
    time_from: int,
    time_till: int,
    points: list[dict],
) -> Path:
    return generate_multi_item_pdf(
        host_name=host_name,
        item_data_list=[{
            "item": {"name": item_name, "units": units},
            "source": source,
            "points": points,
        }],
        time_from=time_from,
        time_till=time_till,
    )
