import asyncio

from app.core.config import settings


def summarize_points(points):
    if not points:
        return {"minimum": None, "average": None, "maximum": None, "samples": 0}
    weights = [max(int(p.get("num", 1)), 1) for p in points]
    return {
        "minimum": min(p.get("min", p["value"]) for p in points),
        "maximum": max(p.get("max", p["value"]) for p in points),
        "average": sum(p["value"] * w for p, w in zip(points, weights)) / sum(weights),
        "samples": sum(weights),
    }


async def collect_items(client, item_ids, time_from, time_till):
    semaphore = asyncio.Semaphore(4)

    async def collect(item_id):
        async with semaphore:
            try:
                result = await client.get_item_data(str(item_id), time_from, time_till)
                if not result["points"]:
                    result["warning"] = "Tidak ada data untuk periode ini."
                return result
            except Exception as exc:
                return {
                    "item": {"itemid": str(item_id), "name": f"Metric {item_id}", "units": ""},
                    "source": "unavailable", "points": [],
                    "warning": str(exc) if isinstance(exc, ValueError) else "Data metrik tidak dapat diambil dari Zabbix.",
                }

    return await asyncio.gather(*(collect(item_id) for item_id in item_ids))
