import math

import httpx

from app.core.config import settings
from app.services.report.data import summarize_points


ITEM_FIELDS = ["itemid", "hostid", "name", "key_", "value_type", "units",
               "status", "state", "history", "trends"]


class ZabbixClient:
    def __init__(self):
        self.url = settings.ZABBIX_URL.rstrip("/")
        self.api_token = settings.ZABBIX_API_TOKEN
        if not self.url or not self.api_token:
            raise RuntimeError("Konfigurasi koneksi Zabbix belum lengkap.")

    async def call(self, method: str, params: dict | None = None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
        headers = {"Content-Type": "application/json-rpc"}
        if method != "apiinfo.version":
            headers["Authorization"] = f"Bearer {self.api_token}"
        async with httpx.AsyncClient(timeout=30, verify=True) as client:
            response = await client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError("Permintaan Zabbix gagal. Periksa koneksi dan hak akses API token.")
        return data["result"]

    async def api_version(self):
        return await self.call("apiinfo.version")

    async def get_hosts(self):
        return await self.call("host.get", {
            "output": ["hostid", "host", "name", "status"],
            "selectInterfaces": ["interfaceid", "ip", "dns", "available"],
            "sortfield": "name", "sortorder": "ASC",
        })

    async def get_host_by_name(self, host_name):
        rows = await self.call("host.get", {
            "output": ["hostid", "host", "name", "status"], "filter": {"name": [host_name]},
        })
        if len(rows) != 1:
            raise ValueError("Host tidak ditemukan atau nama host tidak unik.")
        return rows[0]

    async def validate_selection(self, host_id, host_name, item_ids):
        if host_id:
            hosts = await self.call("host.get", {
                "output": ["hostid", "host", "name", "status"], "hostids": [host_id],
            })
            if len(hosts) != 1:
                raise ValueError("Host tidak ditemukan.")
            host = hosts[0]
        else:
            host = await self.get_host_by_name(host_name)
        items = await self.call("item.get", {"output": ITEM_FIELDS, "itemids": item_ids})
        by_id = {i["itemid"]: i for i in items}
        for item_id in item_ids:
            item = by_id.get(item_id)
            if item is None or item["hostid"] != host["hostid"]:
                raise ValueError("Semua metrik harus berasal dari host yang dipilih.")
            if item["value_type"] not in ("0", "3") or item["status"] != "0":
                raise ValueError("Pilih metrik numerik yang aktif.")
        return host

    async def get_items(self, hostid):
        return await self.call("item.get", {
            "output": ITEM_FIELDS, "hostids": hostid, "sortfield": "name", "sortorder": "ASC",
        })

    async def get_items_by_host_name(self, host_name):
        host = await self.get_host_by_name(host_name)
        return await self.get_items(host["hostid"])

    async def get_item(self, itemid):
        rows = await self.call("item.get", {"output": ITEM_FIELDS, "itemids": itemid})
        if not rows:
            raise ValueError("Metrik tidak ditemukan.")
        return rows[0]

    async def get_graphs(self, hostid):
        return await self.call("graph.get", {
            "output": ["graphid", "name", "width", "height", "graphtype", "show_legend"],
            "hostids": hostid, "selectItems": ["itemid", "name", "value_type", "units"],
            "sortfield": "name", "sortorder": "ASC",
        })

    async def get_history(self, itemid, history_type, time_from, time_till, limit=5000):
        return await self.call("history.get", {
            "output": ["itemid", "clock", "ns", "value"], "history": history_type,
            "itemids": itemid, "time_from": time_from, "time_till": time_till,
            "sortfield": ["clock", "ns"], "sortorder": "ASC", "limit": limit,
        })

    async def get_trends(self, itemid, time_from, time_till, limit=5000):
        return await self.call("trend.get", {
            "output": ["itemid", "clock", "num", "value_min", "value_avg", "value_max"],
            "itemids": itemid, "time_from": time_from, "time_till": time_till,
            "sortfield": "clock", "sortorder": "ASC", "limit": limit,
        })

    async def _complete_history(self, itemid, value_type, start, end):
        result = []
        async def load(left, right):
            rows = await self.get_history(itemid, value_type, left, right)
            if len(rows) >= 5000:
                if left == right:
                    raise ValueError("Terlalu banyak data dalam satu detik. Pilih periode lain.")
                middle = (left + right) // 2
                await load(left, middle)
                await load(middle + 1, right)
            else:
                result.extend(rows)
                if len(result) > settings.MAX_DATA_POINTS:
                    raise ValueError("Data terlalu besar. Pilih periode lebih pendek.")
        await load(start, end)
        return result

    async def get_item_data(self, itemid, time_from, time_till):
        if time_till <= time_from or time_till - time_from > settings.MAX_REPORT_DAYS * 86400:
            raise ValueError(f"Periode harus positif dan maksimal {settings.MAX_REPORT_DAYS} hari.")
        item = await self.get_item(itemid)
        value_type = int(item["value_type"])
        if value_type not in (0, 3):
            raise ValueError("Grafik hanya mendukung metrik numerik.")
        points = []
        source = "history"
        if time_till - time_from > 86400:
            rows = await self.get_trends(itemid, time_from, time_till)
            points = [{
                "timestamp": int(r["clock"]), "value": float(r["value_avg"]),
                "min": float(r["value_min"]), "max": float(r["value_max"]), "num": int(r["num"]),
            } for r in rows]
            source = "trend"
        if not points:
            rows = await self._complete_history(itemid, value_type, time_from, time_till)
            points = [{"timestamp": int(r["clock"]), "value": float(r["value"])} for r in rows]
            source = "history"
        if not points:
            rows = await self.get_trends(itemid, time_from, time_till)
            points = [{
                "timestamp": int(r["clock"]), "value": float(r["value_avg"]),
                "min": float(r["value_min"]), "max": float(r["value_max"]), "num": int(r["num"]),
            } for r in rows]
            source = "trend" if points else source
        if any(not math.isfinite(p[k]) for p in points for k in ("value", "min", "max") if k in p):
            raise ValueError("Zabbix mengembalikan nilai numerik tidak valid.")
        points.sort(key=lambda p: p["timestamp"])
        return {"item": item, "source": source, "time_from": time_from, "time_till": time_till,
                "points": points, "summary": summarize_points(points)}
