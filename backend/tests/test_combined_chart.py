import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from fastapi import HTTPException
from reportlab.platypus import Table

from app.models.requests import GenerateReportRequest
from app.api.v1 import reports
from app.services.report import pdf
from app.services.report.combined import combined_scale, metric_colors


class CombinedChartTests(unittest.TestCase):
    def metrics(self):
        start = int(datetime(2026, 3, 18, tzinfo=ZoneInfo("Asia/Jakarta")).timestamp())
        return start, [{"item": {"itemid": str(i), "name": name, "key_": key, "units": units},
                        "source": "history", "resolution": "minute", "points": [
                            {"timestamp": start + 60, "value": value, "min": value / 2, "max": value * 2, "last": value * 1.5, "num": 2},
                            {"timestamp": start + 86340, "value": value * 2, "last": value * 2.5, "num": 1}]}
                       for i, name, key, units, value in (
                           (10, "Bits received", "net.if.in[wan]", "bps", 1_000_000),
                           (11, "Bits sent", "net.if.out[wan]", "Mbps", 1))]

    def test_unit_normalization_and_incompatible_dimensions(self):
        for units, expected in ((["bps", "Mbps"], [1, 1_000_000]),
                                (["KBps", "bps"], [8192, 1]),
                                (["MB", "Kb"], [8 * 1024**2, 1000]),
                                (["%", "%"], [1, 1])):
            data = [{"item": {"units": unit}, "points": []} for unit in units]
            self.assertEqual(combined_scale(data)[1], expected)
        for units in (("bps", "%"), ("bps", "b"), ("s", "ms")):
            with self.subTest(units=units), self.assertRaisesRegex(ValueError, "satuan sejenis"):
                combined_scale([{"item": {"units": unit}, "points": []} for unit in units])
        _, data = self.metrics()
        data.append({"item": {"units": ""}, "source": "unavailable", "points": []})
        self.assertEqual(combined_scale(data)[0], "bps")

    def test_colors_are_semantic_and_same_direction_lines_have_distinct_patterns(self):
        _, data = self.metrics()
        styles = metric_colors([data[1]["item"], data[0]["item"], data[0]["item"], data[0]["item"]])
        self.assertEqual(styles, [("#dc2626", 0), ("#15803d", 0), ("#15803d", 1), ("#15803d", 2)])

    def test_request_defaults_and_minimum_selection(self):
        base = {"host_name": "Host", "item_ids": ["10"], "time_from": 1, "time_till": 2}
        self.assertEqual(GenerateReportRequest(**base).chart_mode, "separate")
        for changes in ({"chart_mode": "combined"}, {"chart_mode": "stacked"}):
            with self.assertRaises(ValidationError):
                GenerateReportRequest(**{**base, **changes})
        self.assertEqual(GenerateReportRequest(**{**base, "chart_mode": "combined", "item_ids": ["10", "11"]}).chart_mode, "combined")

    def test_daily_combined_pdf_retains_each_metric_statistics_and_empty_days(self):
        start, data = self.metrics()
        original = copy.deepcopy(data)
        parts = []
        build = pdf.SimpleDocTemplate.build
        def capture(document, story, **kwargs):
            parts.extend(story)
            return build(document, story, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(pdf, "REPORT_DIR", Path(directory)), \
             patch.object(pdf.SimpleDocTemplate, "build", autospec=True, side_effect=capture):
            path = pdf.generate_multi_item_pdf("Router", data, start, start + 2 * 86400 - 1,
                                               timezone="Asia/Jakarta", chart_mode="combined")
            self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
        charts = [part for part in parts if isinstance(part, pdf.MetricChart)]
        self.assertEqual(len(charts), 2)
        self.assertEqual(charts[0].data["summary"]["maximum"], 2_000_000)
        self.assertEqual(charts[0].series[1][3], 1_000_000)
        self.assertEqual(charts[0].data["time_from"], start)
        self.assertEqual(charts[1].data["date"], "19-03-2026")
        self.assertEqual(charts[1].data["points"], [])
        tables = [part._cellvalues for part in parts if isinstance(part, Table)]
        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0][0], ["Interface Parameter", "Last", "Min", "Average", "Max"])
        self.assertEqual(tables[0][1][1:], ["2,50 Mbps", "500,00 Kbps", "1,33 Mbps", "2,00 Mbps"])
        self.assertEqual(tables[0][2][1:], tables[0][1][1:])
        self.assertEqual(tables[1][1][1:], ["-", "-", "-", "-"])
        self.assertEqual(data, original)

    def test_missing_series_and_escaped_labels_keep_remaining_graph(self):
        start, data = self.metrics()
        data[1].update(points=[], source="unavailable", warning="No data <private>")
        data[1]["item"].update(name="Sent <router> & link", units="")
        with tempfile.TemporaryDirectory() as directory, patch.object(pdf, "REPORT_DIR", Path(directory)):
            path = pdf.generate_multi_item_pdf("Router", data, start, start + 86399, chart_mode="combined")
            self.assertTrue(path.exists())

    def test_oversized_selection_can_paginate_without_losing_table(self):
        start, data = self.metrics()
        metrics = [{**data[0], "item": {**data[0]["item"], "itemid": str(index), "name": f"Bits received interface {index}"}} for index in range(20)]
        with tempfile.TemporaryDirectory() as directory, patch.object(pdf, "REPORT_DIR", Path(directory)):
            path = pdf.generate_multi_item_pdf("Router", metrics, start, start + 86399, chart_mode="combined")
            self.assertGreater(path.stat().st_size, 1000)


class CombinedReportAPITests(unittest.IsolatedAsyncioTestCase):
    async def report(self, incompatible=False):
        start, data = CombinedChartTests().metrics()
        if incompatible:
            data[1]["item"]["units"] = "%"
        client = MagicMock(validate_selection=AsyncMock(return_value={"hostid": "1", "name": "Router", "host": "router"}),
                           get_item_data=AsyncMock(side_effect=data))
        pool = MagicMock(fetchval=AsyncMock(return_value=1), execute=AsyncMock())
        payload = GenerateReportRequest(host_id="1", host_name="Router", item_ids=["10", "11"],
                                        time_from=start, time_till=start + 86399, chart_mode="combined", include_downtime=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(pdf, "REPORT_DIR", Path(directory)), \
             patch.object(reports, "ZabbixClient", return_value=client), patch.object(reports, "get_pool", return_value=pool), \
             patch.object(reports, "generate_multi_item_pdf", wraps=pdf.generate_multi_item_pdf) as generate:
            if incompatible:
                with self.assertRaises(HTTPException) as caught:
                    await reports.generate_report(payload)
                self.assertEqual(caught.exception.status_code, 422)
                self.assertIn("satuan sejenis", caught.exception.detail)
                self.assertIn("status='FAILED'", pool.execute.call_args.args[0])
                self.assertEqual(list(Path(directory).glob("*.pdf")), [])
            else:
                response = await reports.generate_report(payload)
                self.assertEqual(response.headers["x-report-status"], "SUCCESS")
                self.assertTrue(Path(response.path).read_bytes().startswith(b"%PDF-"))
                self.assertEqual(generate.call_args.kwargs["chart_mode"], "combined")

    async def test_api_renders_combined_pdf_and_tracks_success(self):
        await self.report()

    async def test_api_rejects_incompatible_units_without_creating_pdf(self):
        await self.report(incompatible=True)
