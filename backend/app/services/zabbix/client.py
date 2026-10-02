from wsgiref import headers
from xmlrpc import client

import httpx

from app.core.config import settings


class ZabbixClient:
    def __init__(self):
        self.url = settings.ZABBIX_URL.rstrip("/")
        self.api_token = settings.ZABBIX_API_TOKEN

        if not self.url:
            raise RuntimeError(
                "ZABBIX_URL belum dikonfigurasi."
            )

        if not self.api_token:
            raise RuntimeError(
                "ZABBIX_API_TOKEN belum dikonfigurasi."
            )

    async def call(
        self,
        method: str,
        params: dict | None = None,
    ):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }

        headers = {
            "Content-Type": "application/json-rpc",
            "Authorization": (
                f"Bearer {self.api_token}"
            ),
        }

        async with httpx.AsyncClient(
            timeout=30,
            verify=True,
        ) as client:
            response = await client.post(
                self.url,
                json=payload,
                headers=headers,
        )

        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise RuntimeError(
                data["error"]
            )

        return data["result"]

    async def api_version(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "apiinfo.version",
            "params": {},
            "id": 1,
        }

        async with httpx.AsyncClient(
            timeout=30,
            verify=True,
        ) as client:
            response = await client.post(
                self.url,
                json=payload,
                headers={
                    "Content-Type": "application/json-rpc",
                    "Authorization": f"Bearer {self.api_token}",
                },
            )

        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise RuntimeError(
                data["error"]
            )

        return data["result"]

    async def get_hosts(self):
        return await self.call(
            "host.get",
            {
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status",
                ],
                "selectInterfaces": [
                    "interfaceid",
                    "ip",
                    "dns",
                    "available",
                ],
                "sortfield": "name",
                "sortorder": "ASC",
            },
        )

    async def get_host_by_name(
        self,
        host_name: str,
    ):
        result = await self.call(
            "host.get",
            {
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status",
                ],
                "filter": {
                    "name": [host_name],
                },
            },
        )

        if not result:
            raise RuntimeError(
                f"Host '{host_name}' tidak ditemukan."
            )

        if len(result) > 1:
            raise RuntimeError(
                f"Ditemukan lebih dari satu host "
                f"dengan nama '{host_name}'."
            )

        return result[0]

    async def get_items(
        self,
        hostid: str,
    ):
        return await self.call(
            "item.get",
            {
                "output": [
                    "itemid",
                    "name",
                    "key_",
                    "value_type",
                    "units",
                    "status",
                    "history",
                    "trends",
                ],
                "hostids": hostid,
                "sortfield": "name",
                "sortorder": "ASC",
            },
        )

    async def get_items_by_host_name(
        self,
        host_name: str,
    ):
        return await self.call(
            "item.get",
            {
                "output": [
                    "itemid",
                    "name",
                    "key_",
                    "value_type",
                    "units",
                    "status",
                    "history",
                    "trends",
                ],
                "filter": {
                    "host": host_name,
                },
                "sortfield": "name",
                "sortorder": "ASC",
            },
        )

    async def get_item(
        self,
        itemid: str,
    ):
        result = await self.call(
            "item.get",
            {
                "output": [
                    "itemid",
                    "name",
                    "key_",
                    "value_type",
                    "units",
                    "status",
                    "history",
                    "trends",
                ],
                "itemids": itemid,
            },
        )

        if not result:
            raise RuntimeError(
                f"Item {itemid} tidak ditemukan."
            )

        return result[0]

    async def get_graphs(
        self,
        hostid: str,
    ):
        return await self.call(
            "graph.get",
            {
                "output": [
                    "graphid",
                    "name",
                    "width",
                    "height",
                    "graphtype",
                    "show_legend",
                ],
                "hostids": hostid,
                "selectItems": [
                    "itemid",
                    "name",
                    "value_type",
                    "units",
                ],
                "sortfield": "name",
                "sortorder": "ASC",
            },
        )

    async def get_history(
        self,
        itemid: str,
        history_type: int,
        time_from: int,
        time_till: int,
        limit: int = 5000,
    ):
        return await self.call(
            "history.get",
            {
                "output": [
                    "itemid",
                    "clock",
                    "ns",
                    "value",
                ],
                "history": history_type,
                "itemids": itemid,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

    async def get_trends(
        self,
        itemid: str,
        time_from: int,
        time_till: int,
        limit: int = 5000,
    ):
        return await self.call(
            "trend.get",
            {
                "output": [
                    "itemid",
                    "clock",
                    "num",
                    "value_min",
                    "value_avg",
                    "value_max",
                ],
                "itemids": itemid,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )

    async def get_item_data(
        self,
        itemid: str,
        time_from: int,
        time_till: int,
    ):
        item = await self.get_item(
            itemid
        )

        value_type = int(
            item["value_type"]
        )

        duration = (
            time_till - time_from
        )

        # MVP chart hanya untuk
        # numeric item:
        # 0 = float
        # 3 = unsigned integer
        if value_type not in (0, 3):
            raise RuntimeError(
                "Item bukan numeric. "
                "MVP chart hanya mendukung "
                "value_type 0 atau 3."
            )

        if duration <= 24 * 60 * 60:
            result = await self.get_history(
                itemid=itemid,
                history_type=value_type,
                time_from=time_from,
                time_till=time_till,
            )

            points = [
                {
                    "timestamp": int(
                        row["clock"]
                    ),
                    "value": float(
                        row["value"]
                    ),
                }
                for row in result
            ]

            source = "history"

        else:
            result = await self.get_trends(
                itemid=itemid,
                time_from=time_from,
                time_till=time_till,
            )

            points = [
                {
                    "timestamp": int(
                        row["clock"]
                    ),
                    "value": float(
                        row["value_avg"]
                    ),
                    "min": float(
                        row["value_min"]
                    ),
                    "max": float(
                        row["value_max"]
                    ),
                }
                for row in result
            ]

            source = "trend"

        return {
            "item": item,
            "source": source,
            "time_from": time_from,
            "time_till": time_till,
            "points": points,
        }