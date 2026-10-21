import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import HTTPException

from app.api.v1 import reports
from app.models.requests import GenerateReportRequest
from app.services.report import pdf
from app.services.report.data import collect_items
from app.services.zabbix.client import ZabbixClient


HOST = {"hostid": "1", "host": "router", "name": "Router", "status": "0"}
ITEM = {"itemid": "10", "hostid": "1", "name": "Traffic", "units": "bps", "value_type": "0", "status": "0"}
DATA = {"item": ITEM, "source": "history", "points": [{"timestamp": 120, "value": 1000}]}


class MetricDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = ZabbixClient.__new__(ZabbixClient)
        client.url = "https://zabbix.example/api_jsonrpc.php"
        client.api_token = "test-only-token"
        client.verify = True
        client._api_version = "7.0.0"
        return client

    async def test_first_export_contains_chart_after_two_temporary_history_failures(self):
        attempts = 0

        def respond(request):
            nonlocal attempts
            payload = json.loads(request.content)
            if payload["method"] == "host.get":
                result = [HOST]
            elif payload["method"] == "item.get":
                result = [ITEM]
            else:
                self.assertEqual(payload["method"], "history.get")
                attempts += 1
                if attempts == 1:
                    return httpx.Response(503)
                if attempts == 2:
                    raise httpx.ReadTimeout("temporary read timeout", request=request)
                result = [{"clock": "120", "ns": "0", "value": "1000"}]
            return httpx.Response(200, json={"result": result})

        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(respond)
        pool = MagicMock(fetchval=AsyncMock(return_value=1), execute=AsyncMock())
        payload = GenerateReportRequest(host_id="1", host_name="Router", item_ids=["10"],
                                        time_from=1, time_till=200, include_downtime=False, resolution="minute")
        drawn = []
        original_draw = pdf.MetricChart.draw_series

        def draw(chart, canvas, points, *args):
            drawn.extend(points)
            return original_draw(chart, canvas, points, *args)

        with tempfile.TemporaryDirectory() as folder, patch.object(pdf, "REPORT_DIR", Path(folder)), \
             patch.object(reports, "ZabbixClient", return_value=self.client()), \
             patch.object(reports, "get_pool", return_value=pool), \
             patch.object(pdf.MetricChart, "draw_series", draw), \
             patch("app.services.zabbix.client.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.services.zabbix.client.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw)):
            response = await reports.generate_report(payload)
            contents = Path(response.path).read_bytes()
            self.assertTrue(contents.startswith(b"%PDF-"))
            self.assertIn(b"%%EOF", contents)
            self.assertEqual(response.headers["x-report-status"], "SUCCESS")
            self.assertEqual(attempts, 3)
            self.assertEqual(len(drawn), 1)
            self.assertEqual(drawn[0]["value"], 1000)
            self.assertEqual(len(list(Path(folder).glob("*.pdf"))), 1)

    async def test_permanent_http_and_api_permission_failures_are_not_retried(self):
        client_type = httpx.AsyncClient
        for status, body in ((403, {}), (200, {"error": {"message": "Not authorized"}})):
            requests = []

            def respond(request):
                requests.append(request)
                return httpx.Response(status, json=body)

            transport = httpx.MockTransport(respond)
            with self.subTest(status=status), \
                 patch("app.services.zabbix.client.asyncio.sleep", new_callable=AsyncMock) as delay, \
                 patch("app.services.zabbix.client.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw)):
                with self.assertRaises((httpx.HTTPStatusError, RuntimeError)):
                    await self.client().get_item("10")
                self.assertEqual(len(requests), 1)
                delay.assert_not_awaited()

    async def test_temporary_failure_is_bounded_and_does_not_retry_writes(self):
        client_type = httpx.AsyncClient
        for method, expected in (("history.get", 3), ("host.update", 1)):
            requests = []

            def respond(request):
                requests.append(request)
                return httpx.Response(503)

            transport = httpx.MockTransport(respond)
            with self.subTest(method=method), \
                 patch("app.services.zabbix.client.asyncio.sleep", new_callable=AsyncMock), \
                 patch("app.services.zabbix.client.httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw)):
                with self.assertRaises(httpx.HTTPStatusError):
                    await self.client().call(method, {})
                self.assertEqual(len(requests), expected)

    async def test_failed_metric_prevents_incomplete_pdf_even_when_other_metric_has_data(self):
        async def data(item_id, *_args, **_kwargs):
            if item_id == "11":
                raise httpx.ReadTimeout("unavailable")
            return DATA

        client = MagicMock(validate_selection=AsyncMock(return_value=HOST), get_item_data=AsyncMock(side_effect=data))
        pool = MagicMock(fetchval=AsyncMock(return_value=1), execute=AsyncMock())
        payload = GenerateReportRequest(host_id="1", host_name="Router", item_ids=["10", "11"],
                                        time_from=1, time_till=200, include_downtime=False)
        with patch.object(reports, "ZabbixClient", return_value=client), \
             patch.object(reports, "get_pool", return_value=pool), \
             patch.object(reports, "generate_multi_item_pdf") as generate:
            with self.assertRaises(HTTPException) as caught:
                await reports.generate_report(payload)
            self.assertEqual(caught.exception.status_code, 502)
            generate.assert_not_called()
            self.assertIn("status='FAILED'", pool.execute.call_args.args[0])

    async def test_successful_empty_history_remains_honest_missing_data(self):
        client = MagicMock(get_item_data=AsyncMock(return_value={**DATA, "points": []}))
        result = await collect_items(client, ["10"], 1, 200, "minute")
        self.assertEqual(result[0]["points"], [])
        self.assertEqual(result[0]["source"], "history")
        self.assertIn("Tidak ada data", result[0]["warning"])
        client.get_item_data.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
