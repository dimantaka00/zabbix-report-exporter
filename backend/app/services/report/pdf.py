from datetime import datetime
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Table, TableStyle

from app.core.config import settings
from app.services.report.data import summarize_points

REPORT_DIR = settings.REPORT_STORAGE
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def number(value):
    return "-" if value is None else f"{value:,.3f}".rstrip("0").rstrip(".")


class MetricChart(Flowable):
    def __init__(self, data, timezone):
        super().__init__()
        self.data = data
        self.timezone = timezone
        self.width = 480
        self.height = 335

    def draw(self):
        c = self.canv
        points = self.data["points"]
        if not points:
            c.setFillColor(colors.HexColor("#64748b"))
            c.drawCentredString(240, 160, "No data available for this metric")
            return
        stats = self.data.get("summary") or summarize_points(points)
        low, high = stats["minimum"], stats["maximum"]
        if low == high:
            padding = max(abs(low) * 0.05, 1)
            low, high = low - padding, high + padding
        left, bottom, width, height = 65, 45, 400, 260
        first, last = points[0]["timestamp"], points[-1]["timestamp"]
        span = max(last - first, 1)
        c.setFont("Helvetica", 8)
        for tick in range(5):
            y = bottom + height * tick / 4
            c.setStrokeColor(colors.HexColor("#e2e8f0"))
            c.line(left, y, left + width, y)
            c.setFillColor(colors.HexColor("#475569"))
            c.drawRightString(left - 8, y - 3, number(low + (high - low) * tick / 4))
        for tick in range(3):
            stamp = first + (last - first) * tick / 2
            label = datetime.fromtimestamp(stamp, self.timezone).strftime("%d/%m %H:%M")
            c.drawCentredString(left + width * tick / 2, bottom - 18, label)
        # Retain bucket extrema when rendering dense series.
        plotted = points
        if len(points) > 1000:
            plotted = [points[0]]
            bucket_size = max(len(points) // 450, 1)
            for index in range(0, len(points), bucket_size):
                bucket = points[index:index + bucket_size]
                extrema = [min(bucket, key=lambda p: p["value"]), max(bucket, key=lambda p: p["value"])]
                plotted.extend(sorted(extrema, key=lambda p: p["timestamp"]))
            plotted.append(points[-1])
        c.setStrokeColor(colors.HexColor("#2563eb"))
        c.setFillColor(colors.HexColor("#2563eb"))
        c.setLineWidth(1.2)
        path = c.beginPath()
        for index, point in enumerate(plotted):
            x = left + (point["timestamp"] - first) / span * width
            y = bottom + (point["value"] - low) / (high - low) * height
            if index:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
            if len(points) == 1:
                c.circle(x, y, 3, fill=1, stroke=0)
        c.drawPath(path)


def generate_multi_item_pdf(host_name, item_data_list, time_from, time_till,
                            title="ZABBIX MONITORING REPORT", timezone=None) -> Path:
    tz = ZoneInfo(timezone or settings.TIMEZONE)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / (
        f"zabbix_report_{datetime.now(tz).strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:8]}.pdf"
    )
    temporary = output.with_suffix(".tmp")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#172554")
    styles["Heading2"].textColor = colors.HexColor("#1e3a8a")
    for style in styles.byName.values():
        style.wordWrap = "CJK"
    def text(value):
        return escape(str(value))
    start = datetime.fromtimestamp(time_from, tz).strftime("%d %b %Y %H:%M")
    end = datetime.fromtimestamp(time_till, tz).strftime("%d %b %Y %H:%M")
    story = [
        Paragraph(text(title), styles["Title"]), Spacer(1, 18),
        Paragraph(f"<b>Host:</b> {text(host_name)}", styles["Normal"]),
        Paragraph(f"<b>Period:</b> {start} – {end}", styles["Normal"]),
        Paragraph(f"<b>Timezone:</b> {text(str(tz))}", styles["Normal"]),
        Paragraph(f"<b>Metrics:</b> {len(item_data_list)}", styles["Normal"]),
        Spacer(1, 24), Paragraph("Included metrics", styles["Heading2"]),
    ]
    for index, data in enumerate(item_data_list, 1):
        story.append(Paragraph(f"{index}. {text(data['item']['name'])}", styles["Normal"]))
        story.append(Spacer(1, 6))
    for data in item_data_list:
        story.extend([PageBreak(), Paragraph(text(data["item"]["name"]), styles["Heading2"])])
        story.append(Paragraph(
            f"Unit: {text(data['item'].get('units') or '-')} · Source: {text(data['source'])}",
            styles["Normal"],
        ))
        if data.get("warning"):
            story.append(Paragraph(f"<b>Warning:</b> {text(data['warning'])}", styles["Normal"]))
        story.extend([Spacer(1, 12), MetricChart(data, tz), Spacer(1, 16)])
        stats = data.get("summary") or summarize_points(data["points"])
        summary = Table([
            ["Minimum", "Average", "Maximum", "Samples"],
            [number(stats["minimum"]), number(stats["average"]), number(stats["maximum"]), str(stats["samples"])],
        ], colWidths=[120] * 4)
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ]))
        story.append(summary)

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
                          topMargin=42, bottomMargin=42).build(
            story, onFirstPage=footer, onLaterPages=footer,
        )
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
