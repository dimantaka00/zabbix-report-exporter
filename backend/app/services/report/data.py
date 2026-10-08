import asyncio
from datetime import datetime, timedelta

from app.core.config import settings


def summarize_points(points):
    if not points:
        return {"minimum": None, "average": None, "maximum": None, "last": None, "samples": 0}
    weights = [max(int(p.get("num", 1)), 1) for p in points]
    _, last = max(enumerate(points), key=lambda pair: (
        pair[1].get("timestamp", 0), int(pair[1].get("ns", 0)), pair[0],
    ))
    return {
        "minimum": min(p.get("min", p["value"]) for p in points),
        "maximum": max(p.get("max", p["value"]) for p in points),
        "average": sum(p["value"] * w for p, w in zip(points, weights)) / sum(weights),
        "samples": sum(weights),
        "last": last.get("last", last["value"]),
    }


def minute_points(points):
    """Aggregate actual history samples; leave minutes without samples absent."""
    buckets = {}
    for point in points:
        minute = point["timestamp"] // 60 * 60
        buckets.setdefault(minute, []).append(point)
    result = []
    for stamp, samples in sorted(buckets.items()):
        stats = summarize_points(samples)
        result.append({"timestamp": stamp, "value": stats["average"],
                       "min": stats["minimum"], "max": stats["maximum"],
                       "last": stats["last"], "num": stats["samples"]})
    return result


def daily_data(data, time_from, time_till, timezone):
    """Keep each calendar day separate, including days with no samples."""
    buckets = {}
    for point in data["points"]:
        # A minute bucket starts at :00, even for a partial first minute.
        if time_from // 60 * 60 <= point["timestamp"] <= time_till:
            day = datetime.fromtimestamp(point["timestamp"], timezone).date()
            buckets.setdefault(day, []).append(point)
    day = datetime.fromtimestamp(time_from, timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    last_date = datetime.fromtimestamp(time_till, timezone).date()
    result = []
    while day.date() <= last_date:
        next_day = day + timedelta(days=1)
        points = sorted(buckets.get(day.date(), []), key=lambda point: point["timestamp"])
        result.append({**data, "points": points, "summary": summarize_points(points),
                       "time_from": int(day.timestamp()), "time_till": int(next_day.timestamp()) - 1,
                       "date": day.strftime("%d-%m-%Y")})
        day = next_day
    return result


async def collect_items(client, item_ids, time_from, time_till, resolution="auto"):
    semaphore = asyncio.Semaphore(4)

    async def collect(item_id):
        async with semaphore:
            try:
                result = await client.get_item_data(
                    str(item_id), time_from, time_till, resolution=resolution,
                )
                if not result["points"]:
                    result.setdefault("warning", "Tidak ada data untuk periode ini.")
                return result
            except Exception as exc:
                return {
                    "item": {"itemid": str(item_id), "name": f"Metric {item_id}", "units": ""},
                    "source": "unavailable", "points": [],
                    "warning": str(exc) if isinstance(exc, ValueError) else "Data metrik tidak dapat diambil dari Zabbix.",
                }

    return await asyncio.gather(*(collect(item_id) for item_id in item_ids))
