import math
import ssl
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.report.data import minute_points, summarize_points
from app.services.report.downtime import downtime_result, recommended_trigger


ITEM_FIELDS = ["itemid", "hostid", "name", "key_", "value_type", "units",
               "status", "state", "history", "trends"]


class ZabbixClient:
    SERVERS = {
        "primary": ("Zabbix 1", "ZABBIX_URL", "ZABBIX_API_TOKEN"),
        "secondary": ("Zabbix 2", "ZABBIX_SECONDARY_URL", "ZABBIX_SECONDARY_API_TOKEN"),
    }

    def __init__(self, server_id="primary"):
        if server_id not in self.SERVERS:
            raise ValueError("Sumber Zabbix tidak valid.")
        self.server_id = server_id
        _, url_setting, token_setting = self.SERVERS[server_id]
        self.url = getattr(settings, url_setting).rstrip("/")
        self.api_token = getattr(settings, token_setting)
        self._api_version = None
        if not self.url or not self.api_token:
            raise RuntimeError(f"Konfigurasi {self.SERVERS[server_id][0]} belum lengkap.")
        self.verify = True
        ca_file = settings.ZABBIX_SECONDARY_CA_FILE if server_id == "secondary" else ""
        if ca_file:
            path = Path(ca_file)
            if not path.is_file():
                raise RuntimeError("File CA untuk Zabbix 2 tidak ditemukan di container.")
            self.verify = ssl.create_default_context()
            try:
                self.verify.load_verify_locations(cafile=str(path))
            except (OSError, ssl.SSLError) as exc:
                raise RuntimeError("File CA untuk Zabbix 2 tidak valid.") from exc

    @classmethod
    def configured_servers(cls):
        return [
            {
                "id": server_id,
                "name": name,
                "configured": bool(getattr(settings, url_setting) and getattr(settings, token_setting)),
            }
            for server_id, (name, url_setting, token_setting) in cls.SERVERS.items()
        ]

    async def call(self, method: str, params: dict | None = None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
        headers = {"Content-Type": "application/json-rpc"}
        if method != "apiinfo.version":
            version = await self.api_version()
            try:
                major, minor = (int(part) for part in version.split(".")[:2])
            except (AttributeError, TypeError, ValueError) as exc:
                raise RuntimeError("Versi API Zabbix tidak valid.") from exc
            if (major, minor) < (6, 4):
                payload["auth"] = self.api_token
            else:
                headers["Authorization"] = f"Bearer {self.api_token}"
        async with httpx.AsyncClient(timeout=30, verify=self.verify) as client:
            response = await client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            error = data["error"]
            details = f"{error.get('message', '')} {error.get('data', '')}".lower()
            if "not authorized" in details or "not authorised" in details:
                raise RuntimeError("Zabbix menolak token atau hak akses API. Periksa token baca dan izin user.")
            raise RuntimeError("Permintaan Zabbix gagal. Periksa koneksi dan hak akses API token.")
        return data["result"]

    async def api_version(self):
        if self._api_version is None:
            self._api_version = await self.call("apiinfo.version")
        return self._api_version

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

    async def get_downtime_triggers(self, hostid):
        triggers = await self.call("trigger.get", {
            "hostids": [hostid], "output": ["triggerid", "description", "expression", "value", "status", "state"],
            "selectItems": ["key_"], "selectHosts": ["hostid"], "selectTags": ["tag", "value"],
            "expandExpression": True, "expandDescription": True,
            "sortfield": "description", "sortorder": "ASC",
        })
        return [{"triggerid": trigger["triggerid"], "name": trigger["description"],
                 "value": trigger["value"], "status": trigger["status"], "state": trigger["state"],
                 "recommended": recommended_trigger(trigger)} for trigger in triggers
                if {host["hostid"] for host in trigger.get("hosts", [])} == {str(hostid)}]

    async def get_host_downtime(self, hostid, start, end, trigger_id=None):
        if end <= start or end-start > settings.MAX_REPORT_DAYS*86400:
            raise ValueError(f"Select a valid period of up to {settings.MAX_REPORT_DAYS} days.")
        hosts = await self.call("host.get", {"hostids": [hostid], "output": ["hostid", "name", "host", "status"]})
        if len(hosts) != 1:
            raise ValueError("Host not found.")
        triggers = await self.get_downtime_triggers(hostid)
        candidates = [trigger for trigger in triggers if trigger["triggerid"] == trigger_id] if trigger_id else [
            trigger for trigger in triggers if trigger["recommended"] and trigger["status"] == "0"]
        if trigger_id and not candidates:
            raise ValueError("The downtime trigger must belong to the selected host.")
        if len(candidates) != 1:
            return {"host": hosts[0], "trigger": None, "status": "unconfigured", "current_status": "unknown",
                    "status_at_end": "unknown", "time_from": start, "time_till": end, "events": [],
                    "total_downtime_seconds": None,
                    "warning": "Select a host-down trigger to calculate downtime. Automatic selection requires exactly one active host-down trigger."}
        trigger = candidates[0]
        now = int(time.time())
        cutoff = min(end, now)
        if start > cutoff:
            raise ValueError("The downtime period has not started yet.")
        events, cursor = [], None
        while True:
            params = {"source": 0, "object": 0, "objectids": [trigger["triggerid"]], "value": 1,
                      "problem_time_from": start, "problem_time_till": cutoff,
                      "output": ["eventid", "clock", "value", "r_eventid"],
                      "sortfield": "eventid", "sortorder": "ASC", "limit": 1000}
            if cursor is not None:
                params["eventid_from"] = cursor
            page = await self.call("event.get", params)
            events.extend(page)
            if len(events) > settings.MAX_DATA_POINTS:
                raise ValueError("Too many downtime events. Select a shorter period.")
            if len(page) < 1000:
                break
            next_cursor = str(max(int(event["eventid"]) for event in page)+1)
            if cursor is not None and int(next_cursor) <= int(cursor):
                raise RuntimeError("Zabbix returned incomplete event pagination.")
            cursor = next_cursor
        recovery_ids = sorted({event["r_eventid"] for event in events if event.get("r_eventid", "0") != "0"})
        recoveries = []
        for index in range(0, len(recovery_ids), 1000):
            recoveries.extend(await self.call("event.get", {"source": 0, "object": 0,
                "objectids": [trigger["triggerid"]], "eventids": recovery_ids[index:index+1000],
                "output": ["eventid", "clock", "value"]}))
        latest = await self.call("event.get", {"source": 0, "object": 0, "objectids": [trigger["triggerid"]],
            "time_till": cutoff, "value": [0, 1], "output": ["eventid", "clock", "value"],
            "sortfield": ["clock", "eventid"], "sortorder": "DESC", "limit": 1})
        return downtime_result(hosts[0], trigger, events, recoveries, latest[0] if latest else None, start, end, now)

    async def get_history(self, itemid, history_type, time_from, time_till, limit=5000):
        return await self.call("history.get", {
            "output": ["itemid", "clock", "ns", "value"], "history": history_type,
            "itemids": itemid, "time_from": time_from, "time_till": time_till,
            "sortfield": ["clock"], "sortorder": "ASC", "limit": limit,
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

    async def get_item_data(self, itemid, time_from, time_till, resolution="auto"):
        if time_till <= time_from or time_till - time_from > settings.MAX_REPORT_DAYS * 86400:
            raise ValueError(f"Periode harus positif dan maksimal {settings.MAX_REPORT_DAYS} hari.")
        if resolution not in ("auto", "hourly", "minute"):
            raise ValueError("Resolusi data tidak valid.")
        item = await self.get_item(itemid)
        value_type = int(item["value_type"])
        if value_type not in (0, 3):
            raise ValueError("Grafik hanya mendukung metrik numerik.")
        points = []
        source = "history"
        if resolution == "hourly" or (resolution == "auto" and time_till - time_from > 86400):
            rows = await self.get_trends(itemid, time_from, time_till)
            points = [{
                "timestamp": int(r["clock"]), "value": float(r["value_avg"]),
                "min": float(r["value_min"]), "max": float(r["value_max"]), "num": int(r["num"]), "last": None,
            } for r in rows]
            source = "trend"
        if not points and source == "trend":
            rows = await self._complete_history(itemid, value_type, time_from, time_till)
            points = [{"timestamp": int(r["clock"]), "ns": int(r.get("ns", 0)), "value": float(r["value"])} for r in rows]
            source = "history"
        elif not points:
            rows = await self._complete_history(itemid, value_type, time_from, time_till)
            points = [{"timestamp": int(r["clock"]), "ns": int(r.get("ns", 0)), "value": float(r["value"])} for r in rows]
            source = "history"
        if not points and source == "history" and resolution != "minute":
            rows = await self.get_trends(itemid, time_from, time_till)
            points = [{
                "timestamp": int(r["clock"]), "value": float(r["value_avg"]),
                "min": float(r["value_min"]), "max": float(r["value_max"]), "num": int(r["num"]), "last": None,
            } for r in rows]
            source = "trend" if points else source
        if any(not math.isfinite(p[k]) for p in points for k in ("value", "min", "max") if k in p):
            raise ValueError("Zabbix mengembalikan nilai numerik tidak valid.")
        points.sort(key=lambda p: (p["timestamp"], p.get("ns", 0)))
        if resolution == "minute":
            points = minute_points(points)
        return {"item": item, "source": source, "time_from": time_from, "time_till": time_till,
                "resolution": resolution, "points": points, "summary": summarize_points(points),
                **({"warning": "History tidak tersedia untuk periode ini. Detail per menit memerlukan data history Zabbix."}
                   if resolution == "minute" and not points else {})}
