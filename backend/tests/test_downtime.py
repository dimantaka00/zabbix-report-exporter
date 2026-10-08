import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.services.report import pdf
from app.services.report.downtime import collect_host_downtime, downtime_result, duration_text, duration_detail, recommended_trigger
from app.services.zabbix.client import ZabbixClient

HOST = {"hostid":"1", "name":"Host", "host":"host", "status":"0"}
TRIGGER = {"triggerid":"10", "name":"Unavailable by ICMP ping", "status":"0", "state":"0", "value":"0", "recommended":True}


class DowntimeTests(unittest.TestCase):
    def result(self, events, recoveries=(), latest=None, start=100, end=199, now=300):
        return downtime_result(HOST,TRIGGER,events,recoveries,latest,start,end,now)

    def test_recovery_links_define_full_duration_and_period_overlap(self):
        result=self.result([{"eventid":"1","clock":"90","r_eventid":"2"}],
                           [{"eventid":"2","clock":"210","value":"0"}],{"value":"1"})
        self.assertEqual(result["events"][0],{"event_id":"1","start_time":90,"end_time":210,
            "status":"recovered","duration_seconds":120,"period_duration_seconds":100})
        self.assertEqual(result["total_downtime_seconds"],100)
        self.assertEqual(result["status_at_end"],"offline")
        self.assertEqual(result["current_status"],"online")

    def test_ongoing_downtime_has_no_end_and_uses_observation_time(self):
        result=self.result([{"eventid":"1","clock":"150","r_eventid":"0"}],now=250)
        self.assertEqual(result["events"][0]["end_time"],None)
        self.assertEqual(result["events"][0]["duration_seconds"],100)
        self.assertEqual(result["events"][0]["status"],"ongoing")
        self.assertEqual(result["total_downtime_seconds"],50)

    def test_overlapping_and_duplicate_problems_do_not_double_count_downtime(self):
        events=[{"eventid":"1","clock":"90","r_eventid":"3"},
                {"eventid":"2","clock":"120","r_eventid":"4"},
                {"eventid":"1","clock":"90","r_eventid":"3"}]
        result=self.result(events,[{"eventid":"3","clock":"150","value":"0"},
                                   {"eventid":"4","clock":"160","value":"0"}])
        self.assertEqual(len(result["events"]),2)
        self.assertEqual(result["total_downtime_seconds"],60)

    def test_missing_recovery_is_unknown_rather_than_an_open_outage(self):
        result=self.result([{"eventid":"1","clock":"150","r_eventid":"2"}])
        self.assertEqual(result["events"][0]["status"],"unknown")
        self.assertIsNone(result["events"][0]["duration_seconds"])
        self.assertIsNone(result["total_downtime_seconds"])
        self.assertIn("Recovery",result["warning"])

    def test_empty_events_do_not_claim_historical_online_status(self):
        result=self.result([])
        self.assertEqual(result["status_at_end"],"unknown")
        self.assertEqual(result["total_downtime_seconds"],0)
        trigger={**TRIGGER,"state":"1"}
        self.assertEqual(downtime_result(HOST,trigger,[],[],None,100,199,300)["current_status"],"unknown")

    def test_new_outage_at_observation_time_is_visible_with_zero_elapsed_duration(self):
        result=self.result([{"eventid":"1","clock":"300","r_eventid":"0"}],end=400,now=300)
        self.assertEqual(len(result["events"]),1)
        self.assertEqual(result["events"][0]["duration_seconds"],0)
        self.assertEqual(result["total_downtime_seconds"],0)

    def test_last_second_included_and_outages_recovered_at_start_excluded(self):
        result=self.result([{"eventid":"1","clock":"50","r_eventid":"3"},
                            {"eventid":"2","clock":"199","r_eventid":"4"}],
                           [{"eventid":"3","clock":"100","value":"0"},
                            {"eventid":"4","clock":"210","value":"0"}])
        self.assertEqual([event["event_id"] for event in result["events"]],["2"])
        self.assertEqual(result["total_downtime_seconds"],1)

    def test_auto_detection_excludes_ping_loss_and_interface_events(self):
        ping={"items":[{"key_":"icmpping"}],"expression":"max(/host/icmpping,#3)=0"}
        self.assertTrue(recommended_trigger(ping))
        self.assertFalse(recommended_trigger({**ping,"items":[{"key_":"icmppingloss"}]}))
        self.assertFalse(recommended_trigger({**ping,"expression":"last(/host/icmpping)=1"}))
        self.assertFalse(recommended_trigger({"description":"Interface down","items":[{"key_":"ifOperStatus"}]}))
        self.assertTrue(recommended_trigger({"tags":[{"tag":"report","value":"host-downtime"}]}))

    def test_duration_includes_days_and_seconds(self):
        self.assertEqual(duration_text(90061),"1 d 01:01:01")
        self.assertEqual(duration_text(0),"00:00:00")
        self.assertEqual(duration_text(None),"-")
        self.assertEqual(duration_detail(24540),"6 h 49 m")
        self.assertEqual(duration_detail(59),"59 s")
        self.assertEqual(duration_detail(0),"0 s")

    def test_pdf_adds_one_host_downtime_section_after_daily_charts(self):
        result=self.result([{"eventid":"1","clock":"90","r_eventid":"2"}],
                           [{"eventid":"2","clock":"210","value":"0"}])
        sections=[]
        build=pdf.SimpleDocTemplate.build
        def capture(document,story,**kwargs):
            sections.extend(story)
            return build(document,story,**kwargs)
        metric={"item":{"name":"Traffic","units":"bps"},"source":"history","points":[{"timestamp":120,"value":1000}]}
        with TemporaryDirectory() as folder,patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",autospec=True,side_effect=capture):
            output=pdf.generate_multi_item_pdf("Host",[metric],100,199,timezone="Asia/Jakarta",downtime=result)
            self.assertTrue(output.read_bytes().startswith(b"%PDF-"))
        tables=[part for part in sections if isinstance(part,pdf.Table) and part._cellvalues[0][0]=="No"]
        self.assertEqual(len(tables),1)
        self.assertEqual(len(tables[0]._cellvalues),2)
        self.assertEqual(tables[0].repeatRows,1)
        titles=[part.getPlainText() for part in sections if isinstance(part,pdf.Paragraph)]
        self.assertEqual(titles.count("Downtime Report"),1)
        self.assertEqual(tables[0]._cellvalues[0],["No","Status","Start Time","End Time","Duration"])
        self.assertEqual(tables[0]._cellvalues[1][0],"1")
        self.assertEqual(tables[0]._cellvalues[1][1][0].getPlainText(),"Down")
        downtime_index=titles.index("Downtime Report")
        self.assertFalse(any("Host:" in text or "Trigger:" in text or TRIGGER["name"] in text for text in titles[downtime_index:]))

    def test_available_period_without_outages_has_a_no_downtime_row(self):
        sections=[]
        build=pdf.SimpleDocTemplate.build
        def capture(document,story,**kwargs):
            sections.extend(story)
            return build(document,story,**kwargs)
        with TemporaryDirectory() as folder,patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",autospec=True,side_effect=capture):
            pdf.generate_multi_item_pdf("Hidden name",[],100,199,timezone="Asia/Jakarta",downtime=self.result([]))
        table=next(part for part in sections if isinstance(part,pdf.Table))
        self.assertEqual(table._cellvalues[1],["1","No Downtime","-","-","-"])


class DowntimeClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client=ZabbixClient.__new__(ZabbixClient)
        self.client.get_downtime_triggers=AsyncMock(return_value=[TRIGGER])
        self.client.call=AsyncMock()

    async def test_queries_include_outages_that_started_before_selected_period(self):
        self.client.call.side_effect=[[HOST],[{"eventid":"1","clock":"90","r_eventid":"2"}],
            [{"eventid":"2","clock":"150","value":"0"}],[{"eventid":"2","clock":"150","value":"0"}]]
        with patch("app.services.zabbix.client.time.time",return_value=300):
            result=await self.client.get_host_downtime("1",100,199)
        event_query=self.client.call.await_args_list[1].args[1]
        self.assertEqual(event_query["problem_time_from"],100)
        self.assertNotIn("time_from",event_query)
        self.assertEqual(result["events"][0]["duration_seconds"],60)
        self.assertEqual(result["total_downtime_seconds"],50)
        self.assertEqual(result["status_at_end"],"online")

    async def test_foreign_trigger_rejected_before_reading_any_events(self):
        self.client.call.return_value=[HOST]
        with self.assertRaisesRegex(ValueError,"selected host"):
            await self.client.get_host_downtime("1",100,199,"99")
        self.assertEqual(self.client.call.await_count,1)

    async def test_ambiguous_auto_trigger_is_unconfigured_instead_of_guessed(self):
        self.client.call.return_value=[HOST]
        self.client.get_downtime_triggers.return_value=[TRIGGER,{**TRIGGER,"triggerid":"11"}]
        result=await self.client.get_host_downtime("1",100,199)
        self.assertEqual(result["status"],"unconfigured")
        self.assertIsNone(result["total_downtime_seconds"])

    async def test_event_pagination_handles_more_than_one_thousand_outages(self):
        first=[{"eventid":str(index),"clock":"110","r_eventid":"0"} for index in range(1,1001)]
        self.client.call.side_effect=[[HOST],first,[{"eventid":"1001","clock":"120","r_eventid":"0"}],[]]
        with patch("app.services.zabbix.client.time.time",return_value=300):
            result=await self.client.get_host_downtime("1",100,199)
        self.assertEqual(len(result["events"]),1001)
        self.assertEqual(self.client.call.await_args_list[2].args[1]["eventid_from"],"1001")
        self.assertEqual(result["total_downtime_seconds"],90)

    async def test_collection_failure_preserves_unknown_and_safe_error_message(self):
        self.client.get_host_downtime=AsyncMock(side_effect=RuntimeError("Zabbix menolak izin event"))
        result=await collect_host_downtime(self.client,"1","Host",100,199)
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["total_downtime_seconds"])
        self.assertIn("event read permissions",result["warning"])

    async def test_trigger_list_excludes_multi_host_triggers(self):
        trigger={"triggerid":"10","description":"Ping down","value":"0","state":"0","status":"0",
                 "hosts":[{"hostid":"1"}],"items":[{"key_":"icmpping"}],"expression":"max(/host/icmpping,#3)=0"}
        self.client.call.return_value=[trigger,{**trigger,"triggerid":"11","hosts":[{"hostid":"1"},{"hostid":"2"}]}]
        result=await ZabbixClient.get_downtime_triggers(self.client,"1")
        self.assertEqual([row["triggerid"] for row in result],["10"])
        self.assertTrue(result[0]["recommended"])
