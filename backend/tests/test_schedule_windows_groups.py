import json
import os
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo
from zipfile import ZipFile

from pydantic import ValidationError
from app.api.v1 import auto_schedules, reports, zabbix
from app.core.config import settings
from app.models.requests import AutoScheduleCreate
from app.services.scheduler import auto
from app.services.report import archive
from app.services.zabbix.client import ZabbixClient
import test_auto_schedules as baseline

GROUP={"category":"CS","zabbix_server":"primary","group_id":"10"}
CATALOG=[{**GROUP,"name":"Balai Internet Comnet","suggested_categories":["CS"]},
         {"zabbix_server":"secondary","group_id":"20","name":"TLK-UPS-SR","suggested_categories":["TLK"]}]


class WindowValidationTests(unittest.TestCase):
    def test_defaults_and_invalid_time_date_category_ranges(self):
        policy=AutoScheduleCreate(name="Legacy")
        self.assertEqual((policy.data_start_time,policy.data_end_time,policy.date_start,policy.date_end,policy.host_groups),("00:00","23:59",None,None,[]))
        bad=[{"data_start_time":"24:00"},{"data_end_time":"23:60"},{"data_start_time":"8:00"},
             {"data_start_time":"23:59","data_end_time":"00:00"},
             {"date_start":"2026-10-14","date_end":"2026-10-13"},
             {"host_categories":["CS"]},{"host_groups":[GROUP]},
             {"host_categories":["CS","CS"],"host_groups":[GROUP]},
             {"host_categories":["CS"],"host_groups":[GROUP,GROUP]},
             {"host_categories":["CS"],"host_groups":[{**GROUP,"group_id":"../10"}]},
             {"zabbix_server":"secondary","host_categories":["CS"],"host_groups":[GROUP]}]
        for change in bad:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                AutoScheduleCreate(name="Invalid",**change)
        self.assertEqual(AutoScheduleCreate(name="One minute",data_start_time="23:59",data_end_time="23:59").data_end_time,"23:59")

    def test_daily_window_includes_the_entire_end_minute(self):
        for zone in ["Asia/Jakarta","Asia/Makassar","Asia/Jayapura"]:
            start,end=auto.report_period(date(2026,10,12),zone,"08:15","17:30")
            self.assertEqual(datetime.fromtimestamp(start,ZoneInfo(zone)).strftime("%H:%M:%S"),"08:15:00")
            self.assertEqual(datetime.fromtimestamp(end,ZoneInfo(zone)).strftime("%H:%M:%S"),"17:30:59")
            start,end=auto.report_period(date(2026,10,12),zone,"23:59","23:59")
            self.assertEqual(end-start,59)

    def test_inclusive_execution_dates_and_bounded_catchup(self):
        policy={"timezone":"Asia/Jakarta","hour":7,"minute":0,"last_enqueued_date":None,
                "date_start":date(2026,10,13),"date_end":date(2026,10,15)}
        now=datetime(2026,10,13,7,0,tzinfo=ZoneInfo("Asia/Jakarta"))
        self.assertIsNone(auto.due_date(policy,now-timedelta(days=1)))
        self.assertIsNone(auto.due_date(policy,now-timedelta(minutes=1)))
        self.assertEqual(auto.due_date(policy,now),date(2026,10,13))
        self.assertEqual(auto.due_date(policy,now+timedelta(days=2)),date(2026,10,15))
        self.assertIsNone(auto.due_date(policy,now+timedelta(days=3)))
        self.assertEqual(auto.due_date({**policy,"last_enqueued_date":date(2026,10,13)},now+timedelta(days=10)),date(2026,10,14))
        self.assertIsNone(auto.due_date({**policy,"last_enqueued_date":date(2026,10,15)},now+timedelta(days=10)))


class GroupInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_cs_only_comnet_and_alias_boundaries(self):
        client=MagicMock(get_host_groups=AsyncMock(return_value=[{"groupid":str(i),"name":name} for i,name in enumerate([
            "COMNET","Balai Internet Comnet","CS-UPS-SR","TELKOM","TLK-UPS-SR","ICON-MTIX-SR",
            "Hypernet","Hypervisors","MILES-UPS-SR","NOTCOMNET","ICONIC"],1)]))
        with patch.object(auto,"server_ids",return_value=["primary"]),patch.object(auto,"ZabbixClient",return_value=client):
            rows=await auto.load_host_groups("primary")
        labels={row["name"]:row["suggested_categories"] for row in rows}
        self.assertEqual(labels["COMNET"],["CS"]);self.assertEqual(labels["Balai Internet Comnet"],["CS"])
        for name in ["CS-UPS-SR","Hypervisors","NOTCOMNET","ICONIC"]:self.assertEqual(labels[name],[])
        for name,code in [("TELKOM","TLK"),("TLK-UPS-SR","TLK"),("ICON-MTIX-SR","ICON"),("Hypernet","HYP"),("MILES-UPS-SR","MILES")]:self.assertEqual(labels[name],[code])

    async def test_actual_group_ids_union_sources_and_status_filter(self):
        hosts=[{"hostid":"1","name":"No category in host name","status":"0"},{"hostid":"2","name":"CS host","status":"1"}]
        clients={source:MagicMock(get_hosts=AsyncMock(return_value=hosts)) for source in ["primary","secondary"]}
        with patch.object(auto,"server_ids",return_value=list(clients)),patch.object(auto,"ZabbixClient",side_effect=clients.get):
            rows=await auto.inventory("all","enabled",[GROUP,GROUP])
            self.assertEqual([(s,len(h)) for s,_,h in rows],[("primary",1)])
            clients["primary"].get_hosts.assert_awaited_once_with(["10"])
            clients["secondary"].get_hosts.assert_not_awaited()
            rows=await auto.inventory("all","all",[GROUP,{"zabbix_server":"secondary","group_id":"10"}])
            self.assertEqual([s for s,_,_ in rows],["primary","secondary"])
            clients["secondary"].get_hosts.assert_awaited_once_with(["10"])

    async def test_zabbix_payload_uses_groupids(self):
        with patch.object(settings,"ZABBIX_URL","https://zabbix.example/api_jsonrpc.php"),patch.object(settings,"ZABBIX_API_TOKEN","test-only"):
            client=ZabbixClient("primary")
        with patch.object(client,"call",AsyncMock(return_value=[])) as call:
            await client.get_hosts(["10","20"])
            self.assertEqual(call.await_args.args[0],"host.get")
            self.assertEqual(call.await_args.args[1]["groupids"],["10","20"])
            await client.get_host_groups()
            self.assertEqual(call.await_args.args[0],"hostgroup.get")


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"),"Requires disposable PostgreSQL")
class WindowGroupQueueTests(unittest.IsolatedAsyncioTestCase):
    create=baseline.AutoQueueTests.create
    task=baseline.AutoQueueTests.task

    async def asyncSetUp(self):
        await baseline.AutoQueueTests.asyncSetUp(self)
        self.catalog=AsyncMock(return_value=CATALOG)
        self.patches.extend([patch.object(auto_schedules,"inventory",self.inventory),
            patch.object(auto_schedules,"load_host_groups",self.catalog),patch.object(auto,"load_host_groups",self.catalog),
            patch.object(archive,"REPORT_DIR",Path(self.temp.name)),patch.object(reports,"REPORT_DIR",Path(self.temp.name))])
        for p in self.patches[-5:]:p.start()

    async def asyncTearDown(self):
        await baseline.AutoQueueTests.asyncTearDown(self)

    async def test_api_persists_window_dates_groups_and_edits_preserve_run_snapshot(self):
        today=datetime.now(ZoneInfo("Asia/Jakarta")).date()
        id=await self.create(data_start_time="08:15",data_end_time="17:30",date_start=str(today),date_end=str(today),host_categories=["CS"],host_groups=[GROUP])
        run=await auto.enqueue_schedule(id);self.assertIsNotNone(run)
        self.inventory.assert_awaited_once_with("all","all",[GROUP])
        r=await self.http.put(f"/api/v1/auto-schedules/{id}",json={"name":"Edited","enabled":True,"data_start_time":"10:00","data_end_time":"11:00"})
        self.assertEqual(r.status_code,200,r.text)
        await auto.process_one_task()
        expected=auto.report_period(today-timedelta(days=1),"Asia/Jakarta","08:15","17:30")
        self.assertEqual(self.collect.await_args.args[2:4],expected)
        auto.collect_host_downtime.assert_awaited_once()
        self.assertEqual(auto.collect_host_downtime.await_args.args[3:5],expected)
        while await auto.process_one_task():pass
        self.assertTrue(await archive.archive_run(run))
        filename=await self.pool.fetchval("SELECT archive_filename FROM report_auto_runs WHERE id=$1",run)
        with ZipFile(Path(self.temp.name)/filename) as zipped:
            manifest=json.loads(zipped.read("manifest.json"))
            self.assertEqual((manifest["data_start_time"],manifest["data_end_time"]),("08:15","17:30"))

    async def test_invalid_group_category_missing_group_and_outside_host_are_rejected(self):
        for group in [{**GROUP,"group_id":"999"},{**GROUP,"category":"TLK"}]:
            r=await self.http.post("/api/v1/auto-schedules",json={"name":"Bad group","host_categories":[group["category"]],"host_groups":[group]})
            self.assertEqual(r.status_code,400,r.text)
        r=await self.http.post("/api/v1/auto-schedules",json={"name":"Outside","host_categories":["CS"],"host_groups":[GROUP],"selection_mode":"selected","host_selections":[{"zabbix_server":"primary","host_id":"999","item_ids":None}]})
        self.assertEqual(r.status_code,400,r.text)
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_schedules"),0)

    async def test_group_removed_after_save_defers_execution_without_broadening(self):
        id=await self.create(host_categories=["CS"],host_groups=[GROUP])
        self.catalog.return_value=[]
        self.assertIsNone(await auto.enqueue_schedule(id))
        self.inventory.assert_not_awaited()
        row=await self.pool.fetchrow("SELECT * FROM report_auto_schedules WHERE id=$1",id)
        self.assertIn("Host group",row["last_error"]);self.assertIsNotNone(row["next_retry_at"])
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_tasks"),0)

    async def test_preview_query_ids_are_validated_and_passed_to_inventory(self):
        r=await self.http.get("/api/v1/auto-schedules/preview?group_refs=primary:10")
        self.assertEqual(r.status_code,200,r.text)
        self.inventory.assert_awaited_once_with("all","all",[{"zabbix_server":"primary","group_id":"10"}])
        for path in ["/auto-schedules/preview?group_refs=primary:../10","/auto-schedules/preview?group_refs=unknown:10","/zabbix/hosts?group_ids=../10"]:
            r=await self.http.get("/api/v1"+path);self.assertEqual(r.status_code,422,r.text)
        with patch.object(zabbix,"request",AsyncMock(return_value=[])) as request:
            r=await self.http.get("/api/v1/zabbix/hosts?server_id=primary&group_ids=10&group_ids=20")
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(request.await_args.args,("primary","get_hosts",["10","20"]))

    async def test_future_and_expired_schedules_do_not_enqueue(self):
        today=datetime.now(ZoneInfo("Asia/Jakarta")).date()
        future=await self.create(date_start=str(today+timedelta(days=1)))
        expired=await self.create(date_end=str(today-timedelta(days=1)))
        self.assertIsNone(await auto.enqueue_schedule(future));self.assertIsNone(await auto.enqueue_schedule(expired))
        self.inventory.assert_not_awaited()
        rows=(await self.http.get("/api/v1/auto-schedules")).json()["data"]
        self.assertEqual({r["id"]:r["date_status"] for r in rows},{future:"UPCOMING",expired:"EXPIRED"})
