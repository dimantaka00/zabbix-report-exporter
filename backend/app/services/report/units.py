"""Presentation units: bits use decimal SI; bytes follow Zabbix's 1024 factors."""

from decimal import Decimal, ROUND_HALF_UP, localcontext

BIT_RATE_UNITS = {
    "bps": 1, "b/s": 1, "bit/s": 1, "bits/s": 1,
    "kbps": 1000, "Kbps": 1000,
    "mbps": 1000000, "Mbps": 1000000,
    "gbps": 1000000000, "Gbps": 1000000000,
    "tbps": 1000000000000, "Tbps": 1000000000000,
    "kb/s": 1000, "Kb/s": 1000, "kbit/s": 1000,
    "Mb/s": 1000000, "Mbit/s": 1000000,
    "Gb/s": 1000000000, "Gbit/s": 1000000000,
    "Tb/s": 1000000000000, "Tbit/s": 1000000000000,
}
BYTE_RATE_UNITS = {label: 1024**power for power, label in enumerate(("Bps", "KBps", "MBps", "GBps", "TBps"))}
BYTE_RATE_UNITS.update({label: 1024**power for power, label in enumerate(("B/s", "KB/s", "MB/s", "GB/s", "TB/s"))})
BIT_UNITS = {label: 1000**power for power, label in enumerate(("b", "Kb", "Mb", "Gb", "Tb"))}
BIT_UNITS.update({"kb": 1000, "mb": 1000000, "gb": 1000000000, "tb": 1000000000000})
BYTE_UNITS = {label: 1024**power for power, label in enumerate(("B", "KB", "MB", "GB", "TB"))}
BYTE_UNITS["kB"] = 1024
UNIT_GROUPS = (
    (BIT_RATE_UNITS, 1000, ("bps", "Kbps", "Mbps", "Gbps", "Tbps")),
    (BYTE_RATE_UNITS, 1024, ("Bps", "KBps", "MBps", "GBps", "TBps")),
    (BIT_UNITS, 1000, ("b", "Kb", "Mb", "Gb", "Tb")),
    (BYTE_UNITS, 1024, ("B", "KB", "MB", "GB", "TB")),
)


def unit_group(units):
    return next((group for group in UNIT_GROUPS if (units or "").strip() in group[0]), None)


def is_bandwidth_unit(units):
    return (units or "").strip() in BIT_RATE_UNITS or (units or "").strip() in BYTE_RATE_UNITS


def display_unit(units, peak):
    units = (units or "").strip()
    group = unit_group(units)
    if group is None:
        return 1, units
    sources, step, labels = group
    base = sources[units]
    peak_bps = abs(peak or 0) * base
    for power in reversed(range(len(labels))):
        target, label = step**power, labels[power]
        if peak_bps >= target or target == 1:
            return base / target, label


def bandwidth_number(value):
    """Use Indonesian decimal separators and exactly two decimal places."""
    numeric = Decimal(str(value))
    with localcontext() as context:
        context.prec = max(28, numeric.adjusted() + 3)
        rounded = numeric.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def format_network_value(value, units):
    """Convert once, after aggregation, without binary rounding of the SI factor."""
    units = (units or "").strip()
    group = unit_group(units)
    if group is None:
        return None
    if value is None:
        return "-"
    _, label = display_unit(units, value)
    sources, _, _ = group
    converted = Decimal(str(value)) * Decimal(sources[units]) / Decimal(sources[label])
    return f"{bandwidth_number(converted)} {label}"


def conversion_caption(units):
    group = unit_group(units)
    if group is None:
        return ""
    if group[2][0] == "bps":
        return "Bandwidth: 1 Kbps = 1,000 bps; 1 Mbps = 1,000 Kbps. Lowercase b denotes bits."
    if group[2][0] == "Bps":
        return "Byte rate: 1 KBps = 1,024 Bps; 1 MBps = 1,024 KBps, following Zabbix. Uppercase B denotes bytes."
    if group[2][0] == "b":
        return "Data size: 1 Kb = 1,000 bits; 1 Mb = 1,000 Kb. This unit measures size, not bits per second."
    return "Data size: 1 KB = 1,024 bytes; 1 MB = 1,024 KB, following Zabbix. Uppercase B denotes bytes."
