from datetime import datetime
from pathlib import Path
import re
import unicodedata
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Table, TableStyle,
)

from app.core.config import settings
from app.services.report.data import daily_data, summarize_points
from app.services.report.units import bandwidth_number, display_unit, format_network_value, unit_group, is_bandwidth_unit
from app.services.report.downtime import STATUS_LABELS, duration_text, duration_detail

REPORT_DIR = settings.REPORT_STORAGE
REPORT_DIR.mkdir(parents=True, exist_ok=True)
CONTENT_WIDTH = A4[0] - 84


def report_filename(host_name, time_from, time_till, timezone):
    # Keep readable host names while excluding path separators and special characters.
    name = unicodedata.normalize("NFKC", str(host_name))
    name = "".join(char if char.isalnum() or char in "-_." else "_" for char in name)
    name = re.sub(r"_+", "_", name).strip("._-")
    name = name.encode("utf-8")[:120].decode("utf-8", errors="ignore").rstrip("._-") or "Host"
    start = datetime.fromtimestamp(time_from, timezone).strftime("%Y-%m-%d")
    end = datetime.fromtimestamp(time_till, timezone).strftime("%Y-%m-%d")
    period = start if start == end else f"{start}_{end}"
    return f"{name}_{period}_{uuid4().hex[:8]}.pdf"


def number(value, digits=3):
    return "-" if value is None else f"{value:,.{digits}f}".rstrip("0").rstrip(".")


def display_number(value, unit):
    return bandwidth_number(value) if unit_group(unit) is not None else number(value, 6)


def daily_rows(data, time_from, time_till, timezone):
    rows = []
    for day in daily_data(data, time_from, time_till, timezone):
        stats = day["summary"]
        def value(key):
            bandwidth = format_network_value(stats[key], data.get("item", {}).get("units", ""))
            if bandwidth is not None:
                return bandwidth
            if stats[key] is None:
                return "-"
            factor, unit = display_unit(data.get("item", {}).get("units", ""), stats[key])
            return f"{display_number(stats[key] * factor, unit)} {unit}".strip()
        rows.append([day["date"], value("last"), value("minimum"), value("average"), value("maximum")])
    return rows


class MetricChart(Flowable):
    def __init__(self, data, timezone):
        super().__init__()
        self.data = data
        self.timezone = timezone
        self.width = CONTENT_WIDTH
        self.height = 295

    def draw(self):
        c = self.canv
        points = self.data["points"]
        left, bottom, width, height = 72, 48, self.width - 84, 220
        first, last = self.data["time_from"], self.data["time_till"]
        span = max(last - first, 1)
        stats = self.data.get("summary") or summarize_points(points)
        low, high = (stats["minimum"], stats["maximum"]) if points else (0, 1)
        if low == high:
            padding = max(abs(low) * 0.05, 1)
            low, high = low - padding, high + padding
        factor, unit = display_unit(self.data.get("item", {}).get("units", ""),
                                    max(abs(stats["minimum"] or 0), abs(stats["maximum"] or 0)))
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(left, bottom + height + 10, unit or "Value")
        for tick in range(5):
            y = bottom + height * tick / 4
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(left, y, left + width, y)
            c.setFillColor(colors.HexColor("#475569"))
            c.drawRightString(left - 7, y - 3, display_number((low + (high - low) * tick / 4) * factor, unit))
        start = datetime.fromtimestamp(first, self.timezone)
        for hour in range(24):
            stamp = start.replace(hour=hour).timestamp()
            x = left + (stamp - first) / span * width
            c.setStrokeColor(colors.HexColor("#eef2f7"))
            c.line(x, bottom, x, bottom + height)
            if hour % 3 == 0:
                c.setFillColor(colors.HexColor("#475569"))
                c.drawCentredString(x, bottom - 16, f"{hour:02d}:00")
        for stamp in range(first, last + 1, 60):
            x = left + (stamp - first) / span * width
            c.setStrokeColor(colors.HexColor("#cbd5e1"))
            c.line(x, bottom, x, bottom - (4 if (stamp - first) % 900 == 0 else 1.5))
        c.setFillColor(colors.HexColor("#475569"))
        c.drawRightString(left + width, bottom - 16, "23:59")
        c.drawCentredString(left + width / 2, bottom - 33, "Time (HH:MM)")
        if not points:
            c.drawCentredString(left + width / 2, bottom + height / 2, "No data for this day")
            return
        plotted = points
        if len(points) > 2000:
            plotted = [points[0]]
            bucket_size = max(len(points) // 700, 1)
            for index in range(0, len(points), bucket_size):
                bucket = points[index:index + bucket_size]
                extrema = [min(bucket, key=lambda p: p["value"]), max(bucket, key=lambda p: p["value"])]
                plotted.extend(sorted(extrema, key=lambda p: p["timestamp"]))
            plotted.append(points[-1])
        c.setStrokeColor(colors.HexColor("#93c5fd"))
        c.setLineWidth(0.5)
        for point in plotted:
            if point.get("min", point["value"]) != point.get("max", point["value"]):
                x = left + (point["timestamp"] - first) / span * width
                c.line(x, bottom + (point["min"] - low) / (high - low) * height,
                       x, bottom + (point["max"] - low) / (high - low) * height)
        c.setStrokeColor(colors.HexColor("#2563eb"))
        c.setFillColor(colors.HexColor("#2563eb"))
        c.setLineWidth(0.8)
        path = c.beginPath()
        for index, point in enumerate(plotted):
            x = left + (point["timestamp"] - first) / span * width
            y = bottom + (point["value"] - low) / (high - low) * height
            if index:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
            if len(points) == 1:
                c.circle(x, y, 2.5, fill=1, stroke=0)
        c.drawPath(path)


def table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ])


def generate_multi_item_pdf(host_name, item_data_list, time_from, time_till,
                            title="ZABBIX MONITORING REPORT", timezone=None, downtime=None) -> Path:
    tz = ZoneInfo(timezone or settings.TIMEZONE)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / report_filename(host_name, time_from, time_till, tz)
    temporary = output.with_suffix(".tmp")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#172554")
    styles["Title"].fontSize = 17
    styles["Title"].leading = 21
    styles["Heading2"].textColor = colors.HexColor("#1e3a8a")
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 16
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 12
    styles["BodyText"].fontSize = 8
    styles["BodyText"].leading = 11
    for style in styles.byName.values():
        style.wordWrap = "CJK"

    def text(value):
        return escape(str(value))

    start = datetime.fromtimestamp(time_from, tz).strftime("%d-%m-%Y %H:%M")
    end = datetime.fromtimestamp(time_till, tz).strftime("%d-%m-%Y %H:%M")
    story = [
        Paragraph(text(title), styles["Title"]),
        Paragraph(f"<b>Host:</b> {text(host_name)}", styles["Normal"]),
        Paragraph(f"<b>Period:</b> {start} - {end} | <b>Timezone:</b> {text(str(tz))}", styles["BodyText"]),
        Paragraph(f"<b>Metrics:</b> {len(item_data_list)} | One statistics row per day", styles["BodyText"]),
        Spacer(1, 8),
    ]
    section = 0
    daily_series = [daily_data(data, time_from, time_till, tz) for data in item_data_list]
    for day_index in range(len(daily_series[0]) if daily_series else 0):
        for metric_days in daily_series:
            day = metric_days[day_index]
            if section:
                story.append(PageBreak())
            section += 1
            story.append(Paragraph(f"Date {day['date']}", styles["Heading2"]))
            story.append(Paragraph(text(day['item']['name']), styles["Heading2"]))
            stats = day["summary"]
            _, unit = display_unit(day['item'].get('units'),
                                   max(abs(stats["minimum"] or 0), abs(stats["maximum"] or 0)))
            resolution = day.get("resolution", "minute" if day["source"] == "history" else "hourly")
            detail = {"minute": "Per minute", "hourly": "Per hour", "auto": "Automatic"}.get(resolution, resolution)
            story.append(Paragraph(
                f"{day['date']} | 00:00 - 23:59 | Chart unit: {text(unit or '-')} | "
                f"{text(detail)} | Source: {text(day['source'])}", styles["BodyText"],
            ))
            if day.get("warning"):
                story.append(Paragraph(f"<b>Note:</b> {text(day['warning'])}", styles["BodyText"]))
            story.extend([Spacer(1, 4), MetricChart(day, tz), Spacer(1, 4)])
            summary_rows = daily_rows(day, day["time_from"], day["time_till"], tz)
            for row in summary_rows:
                row[0] = Paragraph(text(day['item']['name']), styles["BodyText"])
            parameter = "Interface Parameter" if is_bandwidth_unit(day['item'].get('units')) else "Parameter"
            summary = Table([[parameter, "Last", "Min", "Average", "Max"], *summary_rows],
                            colWidths=[CONTENT_WIDTH * fraction for fraction in (.32, .17, .17, .17, .17)])
            summary.setStyle(table_style())
            story.append(summary)
    if downtime is not None:
        if section:
            story.append(PageBreak())
        story.append(Paragraph("Downtime Report", styles["Heading2"]))
        story.append(Paragraph(f"<b>Period:</b> {start} - {end} | <b>Timezone:</b> {text(str(tz))}", styles["BodyText"]))
        story.append(Paragraph(
            f"<b>Current status:</b> {STATUS_LABELS.get(downtime.get('current_status'), '-')} | "
            f"<b>Status at period end:</b> {STATUS_LABELS.get(downtime.get('status_at_end'), '-')} | "
            f"<b>Downtime in period:</b> {duration_text(downtime.get('total_downtime_seconds'))}", styles["BodyText"]))
        if downtime.get("warning"):
            story.append(Paragraph(f"<b>Note:</b> {text(downtime['warning'])}", styles["BodyText"]))
        events = downtime.get("events", [])
        if downtime.get("status") == "available":
            def event_time(stamp):
                return datetime.fromtimestamp(stamp, tz).strftime("%d/%m/%Y %H:%M:%S")
            rows = [["No", "Status", "Start Time", "End Time", "Duration"]]
            for index, event in enumerate(events, 1):
                finished = event_time(event['end_time']) if event['end_time'] is not None else (
                    "Ongoing" if event['status'] == 'ongoing' else "Unknown")
                row = [str(index), *[Paragraph(text(value), styles["BodyText"]) for value in (
                    "Down", event_time(event['start_time']), finished)]]
                row.append(Paragraph(f"{duration_detail(event['duration_seconds'])}<br/>{duration_text(event['duration_seconds'])}", styles["BodyText"]))
                rows.append(row)
            if not events:
                rows.append(["1", "No Downtime", "-", "-", "-"])
            table = Table(rows, colWidths=[CONTENT_WIDTH * fraction for fraction in (.07, .18, .26, .26, .23)], repeatRows=1)
            table.setStyle(table_style())
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#70ad47")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.extend([Spacer(1, 10), table])
        as_of = downtime.get("as_of")
        if as_of:
            story.append(Paragraph(f"Updated: {datetime.fromtimestamp(as_of, tz).strftime('%d/%m/%Y %H:%M:%S')}", styles["BodyText"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setTitle(title)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(42, 25, "Generated by Zabbix Report Exporter")
        canvas.drawRightString(A4[0] - 42, 25, f"Page {doc.page}")
        canvas.restoreState()

    try:
        SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=42, leftMargin=42,
                          topMargin=36, bottomMargin=42).build(
            story, onFirstPage=footer, onLaterPages=footer,
        )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
