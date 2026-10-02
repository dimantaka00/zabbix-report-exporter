from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


REPORT_DIR = Path("/app/storage/reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TIMEZONE = ZoneInfo("Asia/Jakarta")


def _draw_item_chart(pdf, item_data, page_number):
    width, height = A4

    item = item_data["item"]
    points = item_data["points"]

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(
        50,
        height - 55,
        item["name"],
    )

    pdf.setFont("Helvetica", 9)

    units = item.get("units") or "-"

    pdf.drawString(
        50,
        height - 75,
        f"Unit: {units}",
    )

    pdf.drawString(
        50,
        height - 90,
        f"Data source: {item_data['source']}",
    )

    if not points:
        pdf.setFont("Helvetica", 12)
        pdf.drawCentredString(
            width / 2,
            height / 2,
            "No data available",
        )

        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            50,
            30,
            f"Page {page_number}",
        )

        pdf.showPage()
        return

    values = [
        float(point["value"])
        for point in points
    ]

    minimum = min(values)
    maximum = max(values)
    average = sum(values) / len(values)

    if minimum == maximum:
        minimum -= 1
        maximum += 1

    chart_x = 55
    chart_y = 190
    chart_width = 485
    chart_height = 350

    pdf.rect(
        chart_x,
        chart_y,
        chart_width,
        chart_height,
    )

    plot_left = chart_x + 40
    plot_right = (
        chart_x + chart_width - 20
    )

    plot_bottom = chart_y + 35
    plot_top = (
        chart_y + chart_height - 20
    )

    plot_width = (
        plot_right - plot_left
    )

    plot_height = (
        plot_top - plot_bottom
    )

    first_timestamp = points[0]["timestamp"]
    last_timestamp = points[-1]["timestamp"]

    timestamp_range = max(
        last_timestamp - first_timestamp,
        1,
    )

    previous_point = None

    for point in points:
        x = (
            plot_left
            + (
                (
                    point["timestamp"]
                    - first_timestamp
                )
                / timestamp_range
            )
            * plot_width
        )

        normalized = (
            point["value"] - minimum
        ) / (
            maximum - minimum
        )

        y = (
            plot_bottom
            + normalized * plot_height
        )

        if previous_point:
            pdf.line(
                previous_point[0],
                previous_point[1],
                x,
                y,
            )

        previous_point = (x, y)

    pdf.setFont("Helvetica", 8)

    pdf.drawString(
        chart_x + 5,
        plot_bottom,
        f"{minimum:.2f}",
    )

    pdf.drawString(
        chart_x + 5,
        plot_top,
        f"{maximum:.2f}",
    )

    pdf.drawString(
        plot_left,
        chart_y + 10,
        datetime.fromtimestamp(
            first_timestamp,
            tz=TIMEZONE,
        ).strftime("%Y-%m-%d %H:%M"),
    )

    end_label = datetime.fromtimestamp(
        last_timestamp,
        tz=TIMEZONE,
    ).strftime("%Y-%m-%d %H:%M")

    pdf.drawRightString(
        plot_right,
        chart_y + 10,
        end_label,
    )

    # Summary
    summary_y = 145

    pdf.setFont("Helvetica-Bold", 10)

    pdf.drawString(
        55,
        summary_y,
        "Summary",
    )

    pdf.setFont("Helvetica", 9)

    pdf.drawString(
        55,
        summary_y - 18,
        f"Minimum: {minimum:.2f}",
    )

    pdf.drawString(
        200,
        summary_y - 18,
        f"Average: {average:.2f}",
    )

    pdf.drawString(
        355,
        summary_y - 18,
        f"Maximum: {maximum:.2f}",
    )

    pdf.setFont("Helvetica", 8)

    pdf.drawString(
        50,
        30,
        f"Page {page_number}",
    )

    pdf.showPage()


def generate_multi_item_pdf(
    host_name: str,
    item_data_list: list[dict],
    time_from: int,
    time_till: int,
    title: str = "ZABBIX MONITORING REPORT",
) -> Path:

    filename = (
        "zabbix_report_"
        f"{datetime.now(TIMEZONE).strftime('%Y%m%d_%H%M%S')}"
        ".pdf"
    )

    output = REPORT_DIR / filename

    pdf = canvas.Canvas(
        str(output),
        pagesize=A4,
    )

    width, height = A4

    # Cover page
    pdf.setTitle(title)

    pdf.setFont(
        "Helvetica-Bold",
        22,
    )

    pdf.drawString(
        50,
        height - 70,
        title,
    )

    pdf.setFont(
        "Helvetica",
        11,
    )

    pdf.drawString(
        50,
        height - 105,
        f"Host: {host_name}",
    )

    start = datetime.fromtimestamp(
        time_from,
        tz=TIMEZONE,
    )

    end = datetime.fromtimestamp(
        time_till,
        tz=TIMEZONE,
    )

    pdf.drawString(
        50,
        height - 125,
        (
            "Period: "
            f"{start.strftime('%Y-%m-%d %H:%M')} "
            "to "
            f"{end.strftime('%Y-%m-%d %H:%M')}"
        ),
    )

    pdf.drawString(
        50,
        height - 145,
        f"Metrics: {len(item_data_list)}",
    )

    pdf.setFont(
        "Helvetica-Bold",
        12,
    )

    pdf.drawString(
        50,
        height - 190,
        "Included Metrics",
    )

    y = height - 215

    pdf.setFont(
        "Helvetica",
        10,
    )

    for index, item_data in enumerate(
        item_data_list,
        start=1,
    ):
        item = item_data["item"]

        pdf.drawString(
            60,
            y,
            f"{index}. {item['name']}",
        )

        y -= 18

        if y < 60:
            pdf.showPage()

            y = height - 60

            pdf.setFont(
                "Helvetica",
                10,
            )

    pdf.drawString(
        50,
        35,
        "Generated by Zabbix Report Exporter",
    )

    pdf.showPage()

    # One page per metric
    for page_number, item_data in enumerate(
        item_data_list,
        start=2,
    ):
        _draw_item_chart(
            pdf,
            item_data,
            page_number,
        )

    pdf.save()

    return output