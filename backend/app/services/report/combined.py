"""Common chart scale and stable colors; statistics retain their source units."""
import re

from app.services.report.units import unit_group

PALETTE = ("#2563eb", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#475569")
RECEIVED = "#15803d"
SENT = "#dc2626"


def metric_colors(items):
    incoming = outgoing = other = 0
    result = []
    for item in items:
        label = f"{item.get('key_', '')} {item.get('name', '')}"
        if re.search(r"net\.if\.out|bits sent|bytes sent|outgoing|transmit", label, re.I):
            result.append((SENT, outgoing % 3))
            outgoing += 1
        elif re.search(r"net\.if\.in|bits received|bytes received|incoming|receive", label, re.I):
            result.append((RECEIVED, incoming % 3))
            incoming += 1
        else:
            result.append((PALETTE[other % len(PALETTE)], (other // len(PALETTE)) % 3))
            other += 1
    return result


def chart_unit(units):
    units = (units or "").strip()
    group = unit_group(units)
    if group is None:
        return units, 1
    sources, _, labels = group
    base = labels[0]
    multiplier = sources[units]
    if base in ("Bps", "B"):
        base = "bps" if base == "Bps" else "b"
        multiplier *= 8
    return base, multiplier


def combined_scale(data):
    units = {chart_unit(metric.get("item", {}).get("units"))[0] for metric in data
             if not (metric.get("source") == "unavailable" and not metric["points"])}
    if len(units) > 1:
        raise ValueError("Grafik gabungan membutuhkan metrik dengan satuan sejenis. Pisahkan bandwidth, ukuran data, dan persentase.")
    unit = next(iter(units), "")
    return unit, [chart_unit(metric.get("item", {}).get("units"))[1] for metric in data]
