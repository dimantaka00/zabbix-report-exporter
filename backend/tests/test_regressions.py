import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from app.api.v1 import dashboard, reports, schedules, zabbix
from app.core import database
from app.models.requests import ScheduleCreate, GenerateReportRequest
from app.services.scheduler import scheduler, jobs
from app.services.scheduler.heartbeat import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, SchedulerHeartbeat
from app.services.report import pdf
from app.services.report.data import daily_data, minute_points, summarize_points
from app.services.report.units import display_unit, format_network_value
from app.services.zabbix.client import ZabbixClient

HOST = {"hostid":"1", "host":"host", "name":"Test host", "status":"0"}
ITEM = {"itemid":"10","hostid":"1","name":"CPU","units":"%","value_type":"0","status":"0"}
DATA = {"item":ITEM,"source":"history","points":[{"timestamp":1,"value":3.0}]}
PAYLOAD = {"name":"Daily test","host_id":"1","host_name":"Test host","item_ids":["10"],"hour":0,"minute":0,"timezone":"Asia/Jakarta","enabled":True}


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_schedule_fields(self):
        for change in ({"hour":24},{"minute":60},{"timezone":"Invalid/Zone"},{"item_ids":[]},
                       {"item_ids":["10","10"]},{"item_ids":["oops"]},{"name":" "},
                       {"item_ids":[str(i) for i in range(21)]},{"unexpected":True}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ScheduleCreate(**{**PAYLOAD,**change})

    def test_rejects_bad_report_period(self):
        base = {"host_name":"Host","item_ids":["10"],"time_from":1,"time_till":2}
        for change in ({"time_till":1},{"time_from":-1},{"time_till":91*86400},
                       {"timezone":"Bad/Zone"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                GenerateReportRequest(**{**base,**change})

    def test_zabbix_source_defaults_to_primary_and_rejects_unknown_sources(self):
        base = {"host_name":"Host","item_ids":["10"],"time_from":1,"time_till":2}
        self.assertEqual(GenerateReportRequest(**base).zabbix_server,"primary")
        with self.assertRaises(ValidationError):
            GenerateReportRequest(**{**base,"zabbix_server":"unknown"})

    def test_constant_and_weighted_statistics(self):
        self.assertEqual(summarize_points([{"value":1},{"value":1}]),
                         {"minimum":1,"maximum":1,"average":1,"samples":2,"last":1})
        summary=summarize_points([{"value":2,"min":0,"max":3,"num":10},
                                  {"value":20,"min":19,"max":22,"num":1}])
        self.assertEqual(summary["minimum"],0)
        self.assertEqual(summary["maximum"],22)
        self.assertAlmostEqual(summary["average"],40/11)
        self.assertEqual(summary["samples"],11)

    def test_pdf_escapes_labels_and_has_unique_atomic_filenames(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pdf,"REPORT_DIR",Path(folder)):
            metric={**DATA,"item":{**ITEM,"name":"CPU <b> & special"}}
            paths=[pdf.generate_multi_item_pdf("Host <bad>",[metric],1,100,"Title & <x>") for _ in range(2)]
            self.assertNotEqual(paths[0],paths[1])
            for path in paths:
                self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
                self.assertRegex(path.name, r"^Host_bad_1970-01-01_[0-9a-f]{8}\.pdf$")
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    def test_report_filename_preserves_host_and_local_period_without_unsafe_paths(self):
        tz=ZoneInfo("Asia/Jakarta")
        start=int(datetime(2026,3,18,tzinfo=tz).timestamp())
        end=int(datetime(2026,4,1,tzinfo=tz).timestamp())-1
        self.assertRegex(pdf.report_filename("Branch Café",start,end,tz),
            r"^Branch_Café_2026-03-18_2026-03-31_[0-9a-f]{8}\.pdf$")
        for host in ["../../Host\\Router:1?*", "..", "東京"*200, "CON"]:
            name=pdf.report_filename(host,start,end,tz)
            self.assertEqual(Path(name).name,name)
            self.assertNotIn("\\",name)
            self.assertNotIn("/",name)
            self.assertFalse(name.startswith("."))
            self.assertLessEqual(len(name.encode("utf-8")),160)

    def test_daily_pdf_rows_combine_all_hours_and_preserve_sample_weights(self):
        timezone=ZoneInfo("Asia/Jakarta")
        first=int(datetime(2026,10,7,8,10,tzinfo=timezone).timestamp())
        rows=pdf.daily_rows({"points":[
            {"timestamp":first,"value":4,"min":2,"max":6,"num":3},
            {"timestamp":first+3600,"value":10,"min":8,"max":12,"num":1},
        ]},first,first+7200,timezone)
        self.assertEqual(rows,[["07-10-2026","10","2","5.5","12"]])

    def test_minute_buckets_keep_extrema_and_counts_without_filling_missing_minutes(self):
        points=minute_points([
            {"timestamp":5,"value":1}, {"timestamp":55,"value":3},
            {"timestamp":125,"value":9},
        ])
        self.assertEqual(points,[
            {"timestamp":0,"value":2,"min":1,"max":3,"num":2,"last":3},
            {"timestamp":120,"value":9,"min":9,"max":9,"num":1,"last":9},
        ])
        self.assertEqual(summarize_points(points)["samples"],3)
        self.assertAlmostEqual(summarize_points(points)["average"],13/3)

    def test_last_keeps_final_raw_sample_instead_of_last_minute_average(self):
        raw=[{"timestamp":70,"ns":200,"value":4000},
             {"timestamp":10,"value":1000}, {"timestamp":70,"ns":100,"value":2000}]
        points=minute_points(raw)
        self.assertEqual(points[-1]["value"],3000)
        self.assertEqual(points[-1]["last"],4000)
        self.assertEqual(summarize_points(points)["last"],4000)
        self.assertEqual(summarize_points(points)["samples"],3)
        self.assertIsNone(summarize_points([])["last"])

    def test_bandwidth_conversion_uses_decimal_units_and_preserves_other_metrics(self):
        for units, peak, expected in (
            ("bps",999999,(.001,"Kbps")), ("bps",1000000,(.000001,"Mbps")),
            ("Kbps",3500,(.001,"Mbps")), ("Mbps",3.5,(1,"Mbps")),
            ("Gbps",2,(1,"Gbps")), ("bps",0,(1,"bps")),
            ("bps",999,(1,"bps")), ("bps",1000,(.001,"Kbps")),
            ("Mbps",.5,(1000,"Kbps")), ("Gbps",1000,(.001,"Tbps")),
            ("%",100,(1,"%")), ("Bps",2000000,(1/1024**2,"MBps")),
        ):
            with self.subTest(units=units,peak=peak):
                self.assertEqual(display_unit(units,peak),expected)

    def test_network_conversion_distinguishes_bits_bytes_sizes_and_rates(self):
        for value, units, expected in (
            (999,"bps","999,00 bps"), (1000,"bps","1,00 Kbps"),
            (2500000,"bps","2,50 Mbps"), (2500,"Kbps","2,50 Mbps"),
            (2.5,"Mbps","2,50 Mbps"), (0.5,"Mbps","500,00 Kbps"),
            (103005,"bps","103,01 Kbps"), (2.5,"Mbit/s","2,50 Mbps"),
            (1024,"Bps","1,00 KBps"), (1024**2,"Bps","1,00 MBps"),
            (2.5,"MBps","2,50 MBps"), (1024,"B/s","1,00 KBps"),
            (1024,"B","1,00 KB"), (1024**2,"B","1,00 MB"),
            (2.5,"MB","2,50 MB"), (2500,"kb","2,50 Mb"),
            (2500000,"b","2,50 Mb"), (0,"bps","0,00 bps"),
            (None,"bps","-"), (None,"Bps","-"),
        ):
            with self.subTest(value=value,units=units):
                self.assertEqual(format_network_value(value,units),expected)
        self.assertIsNone(format_network_value(2500,"%"))
        self.assertIsNone(format_network_value(2500,"!bps"))

    def test_pdf_network_statistics_convert_each_value_from_its_original_unit(self):
        first=1800000000
        for units, values, expected in (
            ("Mbps",[.001,1,2.5],["2,50 Mbps","1,00 Kbps","1,17 Mbps","2,50 Mbps"]),
            ("Bps",[1024,1024**2,2*1024**2],["2,00 MBps","1,00 KBps","1,00 MBps","2,00 MBps"]),
            ("B",[1024,1024**2,2*1024**2],["2,00 MB","1,00 KB","1,00 MB","2,00 MB"]),
        ):
            data={"item":{"units":units},"points":[
                {"timestamp":first+index,"value":value} for index,value in enumerate(values)]}
            self.assertEqual(pdf.daily_rows(data,first,first+60,ZoneInfo("Asia/Jakarta"))[0][1:],expected)

    def test_daily_bandwidth_rows_choose_units_for_each_statistic_and_last(self):
        first=1800000000
        data={"item":{"units":"bps"},"points":minute_points([
            {"timestamp":first,"value":8576},
            {"timestamp":first+3600,"value":3630648},
            {"timestamp":first+3601,"value":1000000},
        ])}
        rows=pdf.daily_rows(data,first,first+7200,ZoneInfo("Asia/Jakarta"))
        self.assertEqual(rows[0][1:],["1,00 Mbps","8,58 Kbps","1,55 Mbps","3,63 Mbps"])
        data["points"]=[{"timestamp":first,"value":8576}]
        self.assertEqual(pdf.daily_rows(data,first,first+60,ZoneInfo("Asia/Jakarta"))[0][1:],
                         ["8,58 Kbps"]*4)
        data["points"]=[{"timestamp":first,"value":2500000}]
        self.assertEqual(pdf.daily_rows(data,first,first+60,ZoneInfo("Asia/Jakarta"))[0][1:],
                         ["2,50 Mbps"]*4)

    def test_network_table_matches_mixed_kbps_and_mbps_reference(self):
        first=1800000000
        data={"item":{"units":"bps"},"points":[
            {"timestamp":first,"value":2690000,"min":11580,"max":13020000,"last":498850,"num":100},
        ]}
        self.assertEqual(pdf.daily_rows(data,first,first+60,ZoneInfo("Asia/Jakarta"))[0][1:],
                         ["498,85 Kbps","11,58 Kbps","2,69 Mbps","13,02 Mbps"])

    def test_daily_series_uses_local_midnight_includes_last_minute_and_empty_days(self):
        tz=ZoneInfo("Asia/Jakarta")
        first=int(datetime(2026,10,7,0,0,tzinfo=tz).timestamp())
        days=daily_data({"points":[{"timestamp":first+86399,"value":2},
                                   {"timestamp":first+86400,"value":8}]},first,first+3*86400-1,tz)
        self.assertEqual([day["date"] for day in days],["07-10-2026","08-10-2026","09-10-2026"])
        self.assertEqual([day["summary"]["samples"] for day in days],[1,1,0])
        self.assertEqual(days[0]["time_from"],first)
        self.assertEqual(days[0]["time_till"],first+86399)
        self.assertIsNone(days[2]["summary"]["average"])

    def test_pdf_has_daily_chart_and_one_summary_without_duplicate_metric_index(self):
        tz=ZoneInfo("Asia/Jakarta")
        start=int(datetime(2026,10,7,0,0,tzinfo=tz).timestamp())
        sections=[]
        build=pdf.SimpleDocTemplate.build
        def capture(document,story,**kwargs):
            sections.extend(story)
            return build(document,story,**kwargs)
        with tempfile.TemporaryDirectory() as folder, patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",autospec=True,side_effect=capture):
            pdf.generate_multi_item_pdf("Host",[DATA],start,start+2*86400-1,timezone="Asia/Jakarta")
        charts=[part for part in sections if isinstance(part,pdf.MetricChart)]
        self.assertEqual(len(charts),2)
        self.assertEqual([chart.data["time_from"] for chart in charts],[start,start+86400])
        first_chart=next(i for i,part in enumerate(sections) if isinstance(part,pdf.MetricChart))
        paragraphs=[part.getPlainText() for part in sections if isinstance(part,pdf.Paragraph)]
        self.assertNotIn("Included metrics",paragraphs)
        self.assertEqual(paragraphs.count("CPU"),2)
        self.assertNotIn("1. CPU",paragraphs)
        self.assertFalse(any(isinstance(part,pdf.PageBreak) for part in sections[:first_chart]))
        summaries=[part for part in sections if isinstance(part,pdf.Table) and part._cellvalues[0][0]=="Parameter"]
        self.assertEqual(len(summaries),2)
        self.assertTrue(all(len(table._cellvalues)==2 for table in summaries))
        self.assertTrue(all("Jam" not in table._cellvalues[0] for table in summaries))
        self.assertTrue(all(table._cellvalues[0][1:]==["Last","Min","Average","Max"] for table in summaries))
        self.assertTrue(all(table._cellvalues[1][0][0].getPlainText()=="CPU" for table in summaries))

    def test_pdf_failure_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",side_effect=RuntimeError("render")):
            with self.assertRaises(RuntimeError):
                pdf.generate_multi_item_pdf("Host",[DATA],1,100)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_monthly_pdf_orders_all_metrics_by_day_and_keeps_daily_statistics(self):
        tz=ZoneInfo("Asia/Jakarta")
        start=int(datetime(2026,3,18,tzinfo=tz).timestamp())
        finish=int(datetime(2026,3,31,23,59,59,tzinfo=tz).timestamp())
        metrics=[{**DATA,"item":{**ITEM,"itemid":str(index),"name":name},
                  "points":[{"timestamp":start+day*86400+120,"value":index+day}
                            for day in range(14) if day!=1]}
                 for index,name in ((10,"Received"),(20,"Sent"))]
        sections=[]
        build=pdf.SimpleDocTemplate.build
        def capture(document,story,**kwargs):
            sections.extend(story)
            return build(document,story,**kwargs)
        with tempfile.TemporaryDirectory() as folder, patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",autospec=True,side_effect=capture):
            output=pdf.generate_multi_item_pdf("Host",metrics,start,finish,timezone="Asia/Jakarta")
            self.assertTrue(output.read_bytes().startswith(b"%PDF-"))
        charts=[part.data for part in sections if isinstance(part,pdf.MetricChart)]
        self.assertEqual([(chart["date"],chart["item"]["name"]) for chart in charts],
                         [(f"{day:02d}-03-2026",name) for day in range(18,32) for name in ("Received","Sent")])
        self.assertEqual([chart["summary"]["last"] for chart in charts[:6]],[10,20,None,None,12,22])
        self.assertEqual([chart["summary"]["last"] for chart in charts[-2:]],[23,33])
        self.assertEqual(charts[0]["time_from"],start)
        self.assertEqual(charts[-1]["time_till"],finish)
        self.assertTrue(all(chart["time_till"]-chart["time_from"]==86399 for chart in charts))


class ZabbixDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client=ZabbixClient.__new__(ZabbixClient)
        self.client.call=AsyncMock(side_effect=[[HOST],[ITEM]])

    async def test_connection_probe_is_authenticated_and_limits_host_output(self):
        self.client.call.side_effect = None
        for rows in ([], [{"hostid": "1"}]):
            self.client.call.return_value = rows
            self.assertTrue(await self.client.check_connection())
            self.client.call.assert_awaited_with("host.get", {"output": ["hostid"], "limit": 1})
        self.client.call.side_effect = RuntimeError("Token denied")
        with self.assertRaisesRegex(RuntimeError, "Token denied"):
            await self.client.check_connection()

    async def test_connection_probe_rejects_malformed_result(self):
        self.client.call.side_effect = None
        self.client.call.return_value = None
        with self.assertRaisesRegex(RuntimeError, "tidak valid"):
            await self.client.check_connection()

    async def test_metric_must_belong_to_host(self):
        self.client.call.side_effect=[[HOST],[{**ITEM,"hostid":"2"}]]
        with self.assertRaisesRegex(ValueError,"host"):
            await self.client.validate_selection("1","ignored",["10"])

    async def test_disabled_hosts_are_listed_and_can_select_their_historical_metrics(self):
        disabled={**HOST,"hostid":"2","name":"Archived router","status":"1"}
        self.client.call.side_effect=[[HOST,disabled],[disabled],[{**ITEM,"hostid":"2"}]]
        self.assertEqual(await self.client.get_hosts(),[HOST,disabled])
        params=self.client.call.call_args.args[1]
        self.assertNotIn("monitored_hosts",params)
        self.assertNotIn("with_monitored_items",params)
        self.assertNotIn("status",params.get("filter",{}))
        self.assertEqual(await self.client.validate_selection("2","ignored",["10"]),disabled)

    async def test_authentication_matches_each_server_version_and_caches_detection(self):
        client_type = httpx.AsyncClient
        for version in ("6.0.42", "6.2.9", "6.4.0", "7.4.10"):
            with self.subTest(version=version):
                requests = []

                def respond(request):
                    payload = json.loads(request.content)
                    requests.append((payload, request.headers))
                    if payload["method"] == "history.get":
                        # Zabbix 6.0 permits only itemid and clock for sorting.
                        if any(field not in ("itemid", "clock") for field in payload["params"]["sortfield"]):
                            return httpx.Response(200, json={"error":{"message":"Invalid params."}})
                        return httpx.Response(200, json={"result":[{"clock":"1", "ns":"0", "value":"3"}]})
                    result = version if payload["method"] == "apiinfo.version" else [HOST]
                    return httpx.Response(200, json={"jsonrpc":"2.0", "result":result, "id":1})

                transport = httpx.MockTransport(respond)
                with patch("app.services.zabbix.client.settings.ZABBIX_URL","https://one/api_jsonrpc.php"), \
                     patch("app.services.zabbix.client.settings.ZABBIX_API_TOKEN","token-one"), \
                     patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_URL","https://two/api_jsonrpc.php"), \
                     patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_API_TOKEN","token-two"), \
                     patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_CA_FILE",""), \
                     patch("app.services.zabbix.client.httpx.AsyncClient",side_effect=lambda **kw: client_type(transport=transport, **kw)):
                    for server_id, token in (("primary", "token-one"), ("secondary", "token-two")):
                        requests.clear()
                        client = ZabbixClient(server_id)
                        self.assertEqual(await client.get_hosts(), [HOST])
                        self.assertEqual(await client.get_hosts(), [HOST])
                        self.assertEqual(await client.get_history("10", 0, 1, 2), [{"clock":"1", "ns":"0", "value":"3"}])
                        self.assertEqual([r[0]["method"] for r in requests], ["apiinfo.version", "host.get", "host.get", "history.get"])
                        self.assertNotIn("auth", requests[0][0])
                        self.assertNotIn("Authorization", requests[0][1])
                        for payload, headers in requests[1:]:
                            if version.startswith(("6.0.", "6.2.")):
                                self.assertEqual(payload["auth"], token)
                                self.assertNotIn("Authorization", headers)
                            else:
                                self.assertNotIn("auth", payload)
                                self.assertEqual(headers["Authorization"], f"Bearer {token}")

    def test_client_selects_server_specific_environment(self):
        with patch("app.services.zabbix.client.settings.ZABBIX_URL","https://one/api_jsonrpc.php"), \
             patch("app.services.zabbix.client.settings.ZABBIX_API_TOKEN","token-one"), \
             patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_URL","https://two/api_jsonrpc.php"), \
             patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_API_TOKEN","token-two"):
            client = ZabbixClient("secondary")
            self.assertEqual(client.url,"https://two/api_jsonrpc.php")
            self.assertEqual(client.api_token,"token-two")

    def test_unconfigured_secondary_server_fails_explicitly(self):
        with patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_URL",""), \
             patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_API_TOKEN",""):
            with self.assertRaisesRegex(RuntimeError,"Zabbix 2"):
                ZabbixClient("secondary")

    def test_secondary_ca_bundle_is_added_without_disabling_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            ca_file=Path(folder)/"ca.pem"
            ca_file.write_text("test CA bundle")
            context=MagicMock()
            with patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_URL","https://two/api_jsonrpc.php"), \
                 patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_API_TOKEN","token-two"), \
                 patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_CA_FILE",str(ca_file)), \
                 patch("app.services.zabbix.client.ssl.create_default_context",return_value=context):
                client=ZabbixClient("secondary")
            self.assertIs(client.verify,context)
            context.load_verify_locations.assert_called_once_with(cafile=str(ca_file))

    def test_configured_missing_secondary_ca_fails_explicitly(self):
        with patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_URL","https://two/api_jsonrpc.php"), \
             patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_API_TOKEN","token-two"), \
             patch("app.services.zabbix.client.settings.ZABBIX_SECONDARY_CA_FILE","/missing/zabbix-ca.pem"):
            with self.assertRaisesRegex(RuntimeError,"CA.*tidak ditemukan"):
                ZabbixClient("secondary")

    async def test_inactive_text_or_missing_metric_rejected(self):
        for items in ([],[{**ITEM,"status":"1"}],[{**ITEM,"value_type":"1"}]):
            self.client.call.side_effect=[[HOST],items]
            with self.assertRaises(ValueError):
                await self.client.validate_selection("1","ignored",["10"])

    async def test_selection_resolves_canonical_name(self):
        self.assertEqual(await self.client.validate_selection("1","untrusted",["10"]),HOST)

    async def test_history_over_5000_is_complete_without_duplicates(self):
        async def history(itemid,value_type,start,end,limit=5000):
            return [{"clock":str(i),"value":"1","ns":"0"} for i in range(start,min(end+1,start+5000))]
        self.client.get_history=history
        rows=await self.client._complete_history("10",0,0,10000)
        self.assertEqual(len(rows),10001)
        self.assertEqual(len({r["clock"] for r in rows}),10001)

    async def test_dense_or_oversized_history_returns_explicit_error(self):
        self.client.get_history=AsyncMock(return_value=[{}]*5000)
        with self.assertRaisesRegex(ValueError,"satu detik"):
            await self.client._complete_history("10",0,1,1)
        self.client.get_history=AsyncMock(return_value=[{"clock":"1"}]*4)
        with patch("app.services.zabbix.client.settings.MAX_DATA_POINTS",3):
            with self.assertRaisesRegex(ValueError,"terlalu besar"):
                await self.client._complete_history("10",0,1,2)

    async def test_trend_extrema_and_weighted_average_are_preserved(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_trends=AsyncMock(return_value=[
            {"clock":"1","value_min":"0","value_max":"10","value_avg":"2","num":"10"},
            {"clock":"3601","value_min":"19","value_max":"22","value_avg":"20","num":"1"}])
        result=await self.client.get_item_data("10",1,100000)
        self.assertEqual(result["source"],"trend")
        self.assertEqual(result["summary"]["maximum"],22)
        self.assertIsNone(result["summary"]["last"])
        self.assertAlmostEqual(result["summary"]["average"],40/11)

    async def test_hourly_resolution_prefers_zabbix_trends_for_a_single_day(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_trends=AsyncMock(return_value=[
            {"clock":"3600","value_min":"1","value_max":"5","value_avg":"3","num":"4"},
        ])
        self.client.get_history=AsyncMock()
        result=await self.client.get_item_data("10",0,86399,resolution="hourly")
        self.assertEqual(result["source"],"trend")
        self.client.get_trends.assert_awaited_once_with("10",0,86399)
        self.client.get_history.assert_not_awaited()

    async def test_minute_resolution_uses_history_even_for_multiple_days(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_history=AsyncMock(return_value=[
            {"clock":"5","value":"1"},{"clock":"55","value":"3"},
            {"clock":"172799","value":"9"},
        ])
        self.client.get_trends=AsyncMock()
        result=await self.client.get_item_data("10",0,172799,resolution="minute")
        self.assertEqual(result["resolution"],"minute")
        self.assertEqual(result["source"],"history")
        self.assertEqual(len(result["points"]),2)
        self.assertEqual(result["summary"]["samples"],3)
        self.assertEqual(result["summary"]["maximum"],9)
        self.client.get_trends.assert_not_awaited()

    async def test_minute_resolution_does_not_replace_missing_history_with_hourly_trends(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_history=AsyncMock(return_value=[])
        self.client.get_trends=AsyncMock()
        result=await self.client.get_item_data("10",0,86399,resolution="minute")
        self.assertEqual(result["points"],[])
        self.assertIn("History",result["warning"])
        self.client.get_trends.assert_not_awaited()

    async def test_nonfinite_values_rejected(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_history=AsyncMock(return_value=[{"clock":"1","value":"NaN"}])
        with self.assertRaisesRegex(ValueError,"tidak valid"):
            await self.client.get_item_data("10",1,2)

    async def test_empty_history_falls_back_to_trends(self):
        self.client.get_item=AsyncMock(return_value=ITEM)
        self.client.get_history=AsyncMock(return_value=[])
        self.client.get_trends=AsyncMock(return_value=[
            {"clock":"1","value_min":"1","value_max":"1","value_avg":"1","num":"3"}])
        self.assertEqual((await self.client.get_item_data("10",1,2))["source"],"trend")


class ServiceStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pool = MagicMock(fetchval=AsyncMock(return_value=1))
        self.redis = MagicMock(ping=AsyncMock(), get=AsyncMock(), aclose=AsyncMock())
        self.zabbix = MagicMock(check_connection=AsyncMock(return_value=True))
        zabbix_factory = MagicMock(return_value=self.zabbix)
        zabbix_factory.configured_servers.return_value = [
            {"id":"primary","name":"Zabbix 7","configured":True},
            {"id":"secondary","name":"Zabbix 2","configured":False},
        ]
        for target, value in (
            ("get_pool", MagicMock(return_value=self.pool)),
            ("create_redis_client", MagicMock(return_value=self.redis)),
            ("ZabbixClient", zabbix_factory),
        ):
            replacement = patch.object(dashboard, target, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.object(dashboard.settings, "REDIS_URL", "redis://test")
        replacement.start()
        self.addCleanup(replacement.stop)

    async def test_status_uses_worker_heartbeat_and_detects_absence(self):
        for heartbeat_value, expected in (
            ("starting", "starting"), ("running", "running"),
            ("error", "error"), (None, "stopped"), ("invalid", "unknown"),
        ):
            with self.subTest(value=heartbeat_value):
                self.redis.get.return_value = heartbeat_value
                result = (await dashboard.dashboard_status())["data"]
                self.assertEqual(result["scheduler"], expected)
                self.assertEqual(result["redis"], "connected")
                self.assertEqual(result["zabbix"], "connected")
                self.assertEqual(result["zabbix_secondary"], "not_configured")
        self.assertEqual(self.redis.aclose.await_count, 5)

    async def test_redis_error_is_unknown_and_connection_is_closed(self):
        self.redis.ping.side_effect = RuntimeError("Redis unavailable")
        result = (await dashboard.dashboard_status())["data"]
        self.assertEqual(result["redis"], "error")
        self.assertEqual(result["scheduler"], "unknown")
        self.redis.aclose.assert_awaited_once()

    async def test_zabbix_servers_are_checked_concurrently(self):
        dashboard.ZabbixClient.configured_servers.return_value[1]["configured"] = True
        started = 0
        both_started = asyncio.Event()

        async def probe():
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            return True

        self.zabbix.check_connection.side_effect = probe
        result = (await asyncio.wait_for(dashboard.dashboard_status(), timeout=1))["data"]
        self.assertEqual(started, 2)
        self.assertEqual(result["zabbix"], "connected")
        self.assertEqual(result["zabbix_secondary"], "connected")
        self.zabbix.get_hosts.assert_not_called()

    async def test_slow_probe_is_cancelled_without_hiding_other_services(self):
        cancelled = asyncio.Event()

        async def slow_probe():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.zabbix.check_connection.side_effect = slow_probe
        self.redis.get.return_value = "running"
        with patch.object(dashboard, "STATUS_CHECK_TIMEOUT", 0.02):
            result = (await dashboard.dashboard_status())["data"]
        self.assertTrue(cancelled.is_set())
        self.assertEqual(result["zabbix"], "error")
        self.assertEqual(result["postgresql"], "connected")
        self.assertEqual(result["redis"], "connected")
        self.assertEqual(result["scheduler"], "running")

    async def test_probe_error_does_not_report_zabbix_connected(self):
        self.zabbix.check_connection.side_effect = RuntimeError("Token denied")
        result = (await dashboard.dashboard_status())["data"]
        self.assertEqual(result["zabbix"], "error")

    async def test_redis_timeout_closes_connection_and_resets_worker_status(self):
        async def slow_heartbeat(_):
            await asyncio.Event().wait()
        self.redis.get.side_effect = slow_heartbeat
        with patch.object(dashboard, "STATUS_CHECK_TIMEOUT", 0.02):
            result = (await dashboard.dashboard_status())["data"]
        self.assertEqual(result["redis"], "error")
        self.assertEqual(result["scheduler"], "unknown")
        self.redis.aclose.assert_awaited_once()

    async def test_worker_heartbeat_has_expiry_and_releases_connection(self):
        client = MagicMock(set=AsyncMock(), aclose=AsyncMock())
        async def stop_after_first_publish(_):
            raise asyncio.CancelledError()
        with patch("app.services.scheduler.heartbeat.create_redis_client", return_value=client), \
             patch("app.services.scheduler.heartbeat.asyncio.sleep", stop_after_first_publish):
            worker = SchedulerHeartbeat()
            worker.status = "error"
            with self.assertRaises(asyncio.CancelledError):
                await worker.run()
        client.set.assert_awaited_once_with(HEARTBEAT_KEY, "error", ex=HEARTBEAT_TTL_SECONDS)
        client.aclose.assert_awaited_once()


class ZabbixRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_hosts_endpoint_uses_the_selected_server(self):
        client = MagicMock(get_hosts=AsyncMock(return_value=[HOST]))
        with patch.object(zabbix,"ZabbixClient",return_value=client) as client_factory:
            result = await zabbix.hosts("secondary")
        client_factory.assert_called_once_with("secondary")
        self.assertEqual(result["data"],[HOST])

    async def test_authorization_errors_are_returned_without_exposing_api_details(self):
        client = MagicMock(get_hosts=AsyncMock(side_effect=RuntimeError(
            "Zabbix menolak token atau hak akses API. Periksa token baca dan izin user.",
        )))
        with patch.object(zabbix,"ZabbixClient",return_value=client):
            with self.assertRaises(HTTPException) as caught:
                await zabbix.request("secondary","get_hosts")
        self.assertEqual(caught.exception.status_code,502)
        self.assertIn("token baca",caught.exception.detail)


class RoutingCompatibilityTests(unittest.TestCase):
    def test_canonical_entry_points_and_routes(self):
        from app.main import app
        from app.FastAPI import app as legacy_app
        from app.services.zabbix.client import ZabbixClient
        from app.services.zabbix_client import ZabbixClient as legacy_client
        self.assertIs(app, legacy_app)
        self.assertIs(ZabbixClient, legacy_client)
        routes = [(route.path, tuple(sorted(route.methods or []))) for route in app.routes]
        self.assertEqual(len(routes), len(set(routes)))
        for path in ("/health", "/api/v1/zabbix/hosts", "/api/v1/reports/generate",
                     "/api/v1/schedules", "/api/v1/history", "/api/v1/dashboard/status"):
            self.assertTrue(any(route[0] == path for route in routes), path)


@unittest.skipUnless(os.getenv("TEST_REDIS_URL"), "Requires a disposable Redis instance")
class RedisIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_heartbeat_and_expiry_are_visible_to_api(self):
        from app.services.scheduler.heartbeat import create_redis_client
        fake_pool = MagicMock(fetchval=AsyncMock(return_value=1))
        fake_zabbix = MagicMock(check_connection=AsyncMock(return_value=True))
        with patch.object(dashboard.settings, "REDIS_URL", os.environ["TEST_REDIS_URL"]), \
             patch.object(dashboard, "get_pool", return_value=fake_pool), \
             patch.object(dashboard, "ZabbixClient", return_value=fake_zabbix):
            client = create_redis_client()
            worker = SchedulerHeartbeat()
            worker.status = "error"
            task = asyncio.create_task(worker.run())
            try:
                async def wait_for_heartbeat():
                    while await client.get(HEARTBEAT_KEY) != "error":
                        await asyncio.sleep(0.05)
                await asyncio.wait_for(wait_for_heartbeat(), timeout=5)
                self.assertTrue(0 < await client.ttl(HEARTBEAT_KEY) <= HEARTBEAT_TTL_SECONDS)
                self.assertEqual((await dashboard.dashboard_status())["data"]["scheduler"], "error")
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await client.expire(HEARTBEAT_KEY, 1)
                await asyncio.sleep(1.1)
                self.assertEqual((await dashboard.dashboard_status())["data"]["scheduler"], "stopped")
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await client.aclose()




@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"),"Requires a disposable PostgreSQL database")
class DatabaseAndAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url_patch=patch.object(database,"DATABASE_URL",os.environ["TEST_DATABASE_URL"])
        self.url_patch.start()
        await database.init_db()
        self.pool=database.get_pool()
        await self.pool.execute("TRUNCATE report_execution_logs, report_schedules RESTART IDENTITY")
        from app.services.access import token_hash
        await self.pool.execute("TRUNCATE app_sessions, access_events, app_users RESTART IDENTITY CASCADE")
        user_id=await self.pool.fetchval("""INSERT INTO app_users(username,display_name,password_hash,role,must_change_password)
            VALUES('regression','Regression','unused','admin',FALSE) RETURNING id""")
        await self.pool.execute("""INSERT INTO app_sessions(token_hash,user_id,csrf_token,ip,ip_kind,user_agent,expires_at)
            VALUES($1,$2,'regression-csrf','127.0.0.1','internal','regression',NOW()+INTERVAL '1 hour')""",
            token_hash('regression-session-token'),user_id)
        self.temp=tempfile.TemporaryDirectory()
        self.client=MagicMock(validate_selection=AsyncMock(return_value=HOST),
                              get_item_data=AsyncMock(return_value=DATA),
                              get_host_by_name=AsyncMock(return_value=HOST),
                              get_host_downtime=AsyncMock(return_value={"status":"available","trigger":None,"events":[],
                                  "current_status":"unknown","status_at_end":"unknown","total_downtime_seconds":0}))
        self.patches=[patch.object(module,"ZabbixClient",return_value=self.client) for module in (jobs,reports,schedules)]
        self.patches += [patch.object(module,"REPORT_DIR",Path(self.temp.name)) for module in (reports,pdf)]
        for p in self.patches:p.start()
        from app.main import app
        self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test",
            cookies={"zabbix_session":"regression-session-token"},headers={"X-CSRF-Token":"regression-csrf"})

    async def asyncTearDown(self):
        await self.http.aclose()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
        await database.close_db()
        self.url_patch.stop()

    async def create(self,**change):
        response=await self.http.post("/api/v1/schedules",json={**PAYLOAD,**change})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()["data"]

    async def row(self,id):
        return await self.pool.fetchrow("SELECT * FROM report_schedules WHERE id=$1",id)

    async def test_concurrent_initialization_preserves_old_history(self):
        log_id=await self.pool.fetchval("INSERT INTO report_execution_logs(status) VALUES('FAILED') RETURNING id")
        bootstrap="import asyncio\nfrom app.core.database import init_db,close_db\nasync def main():\n await init_db()\n await close_db()\nasyncio.run(main())\n"
        processes=await asyncio.gather(*(asyncio.create_subprocess_exec(sys.executable,"-c",bootstrap,
            env={**os.environ,"DATABASE_URL":os.environ["TEST_DATABASE_URL"]}) for _ in range(2)))
        self.assertEqual(await asyncio.gather(*(p.wait() for p in processes)),[0,0])
        self.assertEqual(await self.pool.fetchval("SELECT status FROM report_execution_logs WHERE id=$1",log_id),"FAILED")

    async def test_crud_and_deleted_schedule_preserves_history_identity(self):
        row=await self.create()
        await self.pool.execute("INSERT INTO report_execution_logs(schedule_id,status) VALUES($1,'SUCCESS')",row["id"])
        response=await self.http.put(f"/api/v1/schedules/{row['id']}",json={**PAYLOAD,"name":"Changed","enabled":False})
        self.assertFalse(response.json()["data"]["enabled"])
        self.assertEqual((await self.http.delete(f"/api/v1/schedules/{row['id']}")).status_code,200)
        self.assertEqual((await self.http.get("/api/v1/schedules")).json()["data"],[])
        history=(await self.http.get("/api/v1/history")).json()["data"][0]
        self.assertEqual(history["schedule_name"],"Changed")
        self.assertEqual(history["host_name"],"Test host")

    async def test_invalid_requests_and_host_membership_do_not_insert(self):
        self.assertEqual((await self.http.post("/api/v1/schedules",json={**PAYLOAD,"hour":24})).status_code,422)
        self.client.validate_selection.side_effect=ValueError("Wrong host")
        self.assertEqual((await self.http.post("/api/v1/schedules",json=PAYLOAD)).status_code,400)
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_schedules"),0)

    async def test_manual_report_uses_selected_downtime_trigger_and_can_exclude_downtime(self):
        payload={"host_id":"1","host_name":"Host","item_ids":["10"],"time_from":1,"time_till":100,"downtime_trigger_id":"10"}
        response=await self.http.post("/api/v1/reports/generate",json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.client.get_host_downtime.assert_awaited_once_with("1",1,100,"10")
        self.client.get_host_downtime.reset_mock()
        response=await self.http.post("/api/v1/reports/generate",json={**payload,"include_downtime":False})
        self.assertEqual(response.status_code,200,response.text)
        self.client.get_host_downtime.assert_not_awaited()

    async def test_downtime_api_failure_keeps_metric_report_and_marks_it_partial(self):
        self.client.get_host_downtime.side_effect=RuntimeError("Izin baca event tidak tersedia")
        response=await self.http.post("/api/v1/reports/generate",json={
            "host_name":"Host","item_ids":["10"],"time_from":1,"time_till":100})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers["X-Report-Status"],"PARTIAL")
        log=(await self.http.get("/api/v1/history")).json()["data"][0]
        self.assertIn("Downtime: Downtime data is unavailable",log["error_message"])

    async def test_offline_host_without_metric_samples_can_export_its_downtime(self):
        self.client.get_item_data.return_value={**DATA,"points":[]}
        self.client.get_host_downtime.return_value={"status":"available","trigger":None,"current_status":"online",
            "status_at_end":"online","total_downtime_seconds":89,
            "events":[{"event_id":"1","start_time":1,"end_time":90,"duration_seconds":89,"status":"recovered"}]}
        response=await self.http.post("/api/v1/reports/generate",json={
            "host_name":"Host","item_ids":["10"],"time_from":1,"time_till":100})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers["X-Report-Status"],"PARTIAL")

    async def test_due_schedule_uses_previous_day_once(self):
        row=await self.create()
        result=await jobs.run_schedule(row)
        self.assertEqual(result["status"],"SUCCESS")
        now=datetime.now(ZoneInfo("Asia/Jakarta"))
        day=(now-timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        self.assertEqual(self.client.get_item_data.call_args.args[1:],
                         (int(day.timestamp()),int((day+timedelta(days=1)).timestamp())-1))
        self.assertEqual((await self.row(row["id"]))["last_run_date"],now.date())
        self.assertIsNone(await jobs.run_schedule(row))
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_execution_logs"),1)

    async def test_secondary_source_is_saved_and_used_by_scheduled_run(self):
        row=await self.create(zabbix_server="secondary")
        self.assertEqual(row["zabbix_server"],"secondary")
        with patch.object(jobs,"ZabbixClient",return_value=self.client) as client_factory:
            result=await jobs.run_schedule(row)
        self.assertEqual(result["status"],"SUCCESS")
        client_factory.assert_called_once_with("secondary")
        self.assertEqual(self.client.get_item_data.await_args.kwargs["resolution"],"minute")

    async def test_disabled_schedule_skipped_but_run_now_allowed(self):
        row=await self.create(enabled=False)
        self.assertIsNone(await jobs.run_schedule(row))
        response=await self.http.post(f"/api/v1/schedules/{row['id']}/run")
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.http.get("/api/v1/history")).json()["data"][0]["trigger_type"],"manual_schedule")

    async def test_future_scheduled_time_skipped(self):
        row=await self.create(hour=23,minute=59)
        class Morning(datetime):
            @classmethod
            def now(cls,tz=None):
                return datetime.now(tz).replace(hour=10,minute=0)
        with patch.object(jobs,"datetime",Morning):
            self.assertIsNone(await jobs.run_schedule(row))
        self.client.get_item_data.assert_not_awaited()

    async def test_no_data_retry_survives_pool_restart_and_recovers(self):
        row=await self.create()
        self.client.get_item_data.return_value={**DATA,"points":[]}
        self.assertFalse(await jobs.run_schedule(row))
        updated=await self.row(row["id"])
        self.assertIsNone(updated["last_run_date"])
        self.assertIsNotNone(updated["next_retry_at"])
        await database.close_db()
        await database.init_db()
        self.pool=database.get_pool()
        self.assertFalse(await jobs.run_schedule(row))
        self.assertEqual(self.client.get_item_data.await_count,1)
        await self.pool.execute("UPDATE report_schedules SET next_retry_at=NOW()-INTERVAL '1 minute'")
        self.client.get_item_data.return_value=DATA
        self.assertEqual((await jobs.run_schedule(row))["status"],"SUCCESS")
        self.assertIsNone((await self.row(row["id"]))["next_retry_at"])

    async def test_partial_data_is_labeled_and_names_missing_metric(self):
        row=await self.create(item_ids=["10","11"])
        async def data(id,*_,resolution="auto"):
            return DATA if id=="10" else {**DATA,"item":{**ITEM,"name":"Missing memory"},"points":[]}
        self.client.get_item_data.side_effect=data
        result=await jobs.run_schedule(row)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertIn("Missing memory",result["warning"])
        self.assertEqual((await self.http.get("/api/v1/history")).json()["data"][0]["status"],"PARTIAL")

    async def test_pdf_failure_persists_failed_state_without_completed_day(self):
        row=await self.create()
        with patch.object(jobs,"generate_multi_item_pdf",side_effect=RuntimeError("render")):
            self.assertFalse(await jobs.run_schedule(row))
        self.assertIsNone((await self.row(row["id"]))["last_run_date"])
        self.assertEqual((await self.http.get("/api/v1/history")).json()["data"][0]["status"],"FAILED")

    async def test_concurrent_run_edit_delete_and_toggle_are_locked(self):
        row=await self.create()
        entered,release=asyncio.Event(),asyncio.Event()
        async def slow(*_,resolution="auto"):
            entered.set();await release.wait();return DATA
        self.client.get_item_data.side_effect=slow
        task=asyncio.create_task(jobs.run_schedule(row))
        try:
            await asyncio.wait_for(entered.wait(),5)
            self.assertIsNone(await jobs.run_schedule(row))
            for method,path,body in (
                ("POST",f"/api/v1/schedules/{row['id']}/run",None),
                ("PUT",f"/api/v1/schedules/{row['id']}",PAYLOAD),
                ("DELETE",f"/api/v1/schedules/{row['id']}",None),
                ("PATCH",f"/api/v1/schedules/{row['id']}/status",{"enabled":False})):
                response=await self.http.request(method,path,json=body)
                self.assertEqual(response.status_code,409,response.text)
        finally:
            release.set()
            await task
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_execution_logs"),1)

    async def test_interrupted_run_is_repaired_and_lock_released(self):
        row=await self.create()
        entered=asyncio.Event()
        async def slow(*_,resolution="auto"):
            entered.set();await asyncio.Event().wait()
        self.client.get_item_data.side_effect=slow
        task=asyncio.create_task(jobs.run_schedule(row))
        await asyncio.wait_for(entered.wait(),5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.client.get_item_data.side_effect=None
        self.assertEqual((await jobs.run_schedule(row))["status"],"SUCCESS")
        statuses=await self.pool.fetch("SELECT status FROM report_execution_logs ORDER BY id")
        self.assertEqual([r["status"] for r in statuses],["FAILED","SUCCESS"])

    async def test_manual_report_download_history_and_pagination(self):
        payload={"host_id":"1","host_name":"ignored","item_ids":["10"],"time_from":1,"time_till":100,"title":"Manual"}
        response=await self.http.post("/api/v1/reports/generate",json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers["x-report-status"],"SUCCESS")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(self.client.get_item_data.await_args.kwargs["resolution"],"minute")
        history=(await self.http.get("/api/v1/history?limit=1")).json()
        self.assertEqual(history["total"],1)
        self.assertEqual(history["data"][0]["host_name"],"Test host")
        self.assertEqual(history["data"][0]["trigger_type"],"manual_report")
        filename=history["data"][0]["report_filename"]
        self.assertRegex(filename,r"^Test_host_1970-01-01_[0-9a-f]{8}\.pdf$")
        self.assertIn(filename,response.headers["content-disposition"])
        archive=(await self.http.get("/api/v1/reports?limit=1")).json()
        self.assertEqual(archive["total"],1)
        self.assertEqual(archive["data"][0]["filename"],filename)
        self.assertEqual((await self.http.get(archive["data"][0]["download_url"])).content,response.content)
        self.assertEqual((await self.http.get("/api/v1/history?offset=1")).json()["data"],[])

    async def test_unicode_host_filename_downloads_from_generation_and_archive(self):
        self.client.validate_selection.return_value={**HOST,"name":"Branch Café"}
        response=await self.http.post("/api/v1/reports/generate",json={
            "host_id":"1","host_name":"ignored","item_ids":["10"],"time_from":1,"time_till":100})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn("filename*=utf-8''Branch_Caf%C3%A9_",response.headers["content-disposition"])
        archive=(await self.http.get("/api/v1/reports?limit=1")).json()["data"][0]
        self.assertTrue(archive["filename"].startswith("Branch_Café_"))
        self.assertIn("Caf%C3%A9",archive["download_url"])
        download=await self.http.get(archive["download_url"])
        self.assertEqual(download.status_code,200)
        self.assertEqual(download.content,response.content)
        self.assertEqual(download.headers["content-disposition"],response.headers["content-disposition"])

    async def test_disabled_host_can_generate_a_report_from_retained_history(self):
        self.client.validate_selection.return_value={**HOST,"status":"1"}
        response=await self.http.post("/api/v1/reports/generate",json={
            "host_id":"1","host_name":"Test host","item_ids":["10"],"time_from":1,"time_till":100,
            "include_downtime":False})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers["x-report-status"],"SUCCESS")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.client.get_item_data.assert_awaited_once()

    async def test_empty_manual_report_is_failed_without_creating_pdf(self):
        self.client.get_item_data.return_value={**DATA,"points":[]}
        response=await self.http.post("/api/v1/reports/generate",json={
            "host_name":"Host","item_ids":["10"],"time_from":1,"time_till":100})
        self.assertEqual(response.status_code,422,response.text)
        self.assertEqual((await self.http.get("/api/v1/history")).json()["data"][0]["status"],"FAILED")
        self.assertFalse(list(Path(self.temp.name).glob("*.pdf")))

    async def test_bad_download_paths_and_non_pdf_are_rejected(self):
        (Path(self.temp.name)/"secret.txt").write_text("secret")
        self.assertEqual((await self.http.get("/api/v1/reports/secret.txt")).status_code,400)
        self.assertEqual((await self.http.get("/api/v1/reports/missing.pdf")).status_code,404)
        self.assertEqual((await self.http.get("/api/v1/reports/%2e%2e%2fsecret.txt")).status_code,404)

    async def test_poll_error_recovery_and_disabled_failure_health(self):
        row=await self.create()
        await self.pool.execute("UPDATE report_schedules SET last_error='Failed',enabled=FALSE")
        await scheduler.process_schedules()
        self.assertEqual(scheduler.heartbeat.status,"running")
        await self.pool.execute("UPDATE report_schedules SET enabled=TRUE,next_retry_at=NOW()+INTERVAL '1 minute'")
        await scheduler.process_schedules()
        self.assertEqual(scheduler.heartbeat.status,"error")
        await self.pool.execute("UPDATE report_schedules SET next_retry_at=NULL")
        await scheduler.process_schedules()
        self.assertEqual(scheduler.heartbeat.status,"running")

    async def test_database_outage_marks_worker_error(self):
        with patch.object(scheduler,"get_pool",side_effect=RuntimeError("offline")):
            await scheduler.process_schedules()
        self.assertEqual(scheduler.heartbeat.status,"error")

    async def test_completed_partial_report_warning_does_not_mark_scheduler_unhealthy(self):
        await self.create()
        await self.pool.execute("""UPDATE report_schedules SET last_run_date=$1,next_retry_at=NULL,
            last_error='Downtime: trigger belum dikonfigurasi.'""", datetime.now(ZoneInfo("Asia/Jakarta")).date())
        await scheduler.process_schedules()
        self.assertEqual(scheduler.heartbeat.status,"running")
        self.assertEqual(await self.pool.fetchval("SELECT last_error FROM report_schedules"),
                         "Downtime: trigger belum dikonfigurasi.")

    async def test_readiness_endpoint_checks_database(self):
        self.assertEqual((await self.http.get("/health/ready")).status_code,200)

    async def test_interrupted_manual_report_eventually_expires_without_touching_recent_request(self):
        entered=asyncio.Event()
        async def slow(*_,resolution="auto"):
            entered.set()
            await asyncio.Event().wait()
        self.client.get_item_data.side_effect=slow
        task=asyncio.create_task(self.http.post("/api/v1/reports/generate",json={
            "host_name":"Host","item_ids":["10"],"time_from":1,"time_till":100}))
        await asyncio.wait_for(entered.wait(),5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        await self.pool.execute("UPDATE report_execution_logs SET started_at=NOW()-INTERVAL '5 minutes'")
        recent_id=await self.pool.fetchval("INSERT INTO report_execution_logs(status,trigger_type) VALUES('RUNNING','manual_report') RETURNING id")
        await scheduler.process_schedules()
        statuses=await self.pool.fetch("SELECT id,status,finished_at FROM report_execution_logs ORDER BY id")
        self.assertEqual(statuses[0]["status"],"FAILED")
        self.assertIsNotNone(statuses[0]["finished_at"])
        self.assertEqual(statuses[1]["id"],recent_id)
        self.assertEqual(statuses[1]["status"],"RUNNING")

    async def test_stale_log_with_live_schedule_lock_is_preserved(self):
        row=await self.create()
        log_id=await self.pool.fetchval("""
            INSERT INTO report_execution_logs(schedule_id,status,started_at)
            VALUES($1,'RUNNING',NOW()-INTERVAL '5 minutes') RETURNING id
        """,row["id"])
        async with self.pool.acquire() as conn:
            await conn.fetchval("SELECT pg_advisory_lock($1::int,$2::int)",jobs.LOCK_NAMESPACE,row["id"])
            try:
                await scheduler.process_schedules()
                self.assertEqual(await self.pool.fetchval("SELECT status FROM report_execution_logs WHERE id=$1",log_id),"RUNNING")
            finally:
                await conn.fetchval("SELECT pg_advisory_unlock($1::int,$2::int)",jobs.LOCK_NAMESPACE,row["id"])
        await scheduler.process_schedules()
        self.assertEqual(await self.pool.fetchval("SELECT status FROM report_execution_logs WHERE id=$1",log_id),"FAILED")
