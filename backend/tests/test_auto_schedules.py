import asyncio
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError
from app.core import database
from app.core.config import settings
from app.models.requests import AutoScheduleCreate
from app.services.scheduler import auto
from app.services.report import pdf


class AutoTimeTests(unittest.TestCase):
    def test_full_day_time_range_and_validation(self):
        for hour, minute in [(0,0),(23,59)]:
            self.assertEqual(AutoScheduleCreate(name="Daily",hour=hour,minute=minute).hour,hour)
        for values in [{"hour":24},{"minute":60},{"hour":-1},{"timezone":"Bad/Zone"},{"zabbix_server":"unknown"},{"host_status":"unknown"},{"name":" "},{"item_ids":["1"]}]:
            with self.subTest(values=values),self.assertRaises(ValidationError):
                AutoScheduleCreate(**{"name":"Daily",**values})

    def test_due_time_midnight_last_minute_and_catchup(self):
        policy={"timezone":"Asia/Jakarta","hour":23,"minute":59,"last_enqueued_date":None}
        now=datetime(2026,10,12,23,58,tzinfo=ZoneInfo("Asia/Jakarta"))
        self.assertIsNone(auto.due_date(policy,now))
        self.assertEqual(auto.due_date(policy,now+timedelta(minutes=1)),date(2026,10,12))
        self.assertEqual(auto.due_date({**policy,"hour":0,"minute":0},now.replace(hour=0,minute=0)),date(2026,10,12))
        self.assertEqual(auto.due_date({**policy,"last_enqueued_date":date(2026,10,9)},now),date(2026,10,10))
        self.assertIsNone(auto.due_date({**policy,"last_enqueued_date":date(2026,10,12)},now+timedelta(minutes=1)))

    def test_period_is_previous_complete_local_day(self):
        for timezone in ["Asia/Jakarta","Asia/Makassar","Asia/Jayapura"]:
            start,end=auto.report_period(date(2026,10,11),timezone)
            self.assertEqual(end-start,86399)
            self.assertEqual(datetime.fromtimestamp(start,ZoneInfo(timezone)).isoformat()[:19],"2026-10-11T00:00:00")
            self.assertEqual(datetime.fromtimestamp(end,ZoneInfo(timezone)).isoformat()[:19],"2026-10-11T23:59:59")


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"),"Requires disposable PostgreSQL")
class AutoQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_patch=patch.object(database,"DATABASE_URL",os.environ["TEST_DATABASE_URL"]);self.db_patch.start()
        await database.init_db();self.pool=database.get_pool()
        await self.pool.execute("TRUNCATE report_auto_tasks,report_auto_runs,report_auto_schedules,report_execution_logs RESTART IDENTITY CASCADE")
        self.temp=tempfile.TemporaryDirectory()
        self.items=[{"itemid":str(i),"name":f"Metric {i}","value_type":"0","status":"0","units":"%"} for i in range(1,26)]
        self.items[-1]["value_type"]="3"
        self.client=MagicMock(get_items=AsyncMock(return_value=self.items))
        self.client.get_items.side_effect=lambda host:self.items if host=="1" else []
        self.host={"hostid":"1","name":"Router","status":"0"}
        self.inventory=AsyncMock(return_value=[("primary",[self.host],[self.host])])
        async def collect(client,ids,start,end,resolution):
            return [{"item":next(i for i in self.items if i["itemid"]==id),"points":[{"timestamp":start,"value":1}],"source":"history"} for id in ids]
        self.collect=AsyncMock(side_effect=collect)
        self.patches=[patch.object(auto,"inventory",self.inventory),patch.object(auto,"ZabbixClient",return_value=self.client),
            patch.object(auto,"collect_items",self.collect),patch.object(auto,"collect_host_downtime",AsyncMock(return_value={"events":[]})),
            patch.object(pdf,"REPORT_DIR",Path(self.temp.name)),patch.object(settings,"AUTH_ENABLED",False)]
        from app.api.v1 import auto_schedules
        self.patches.append(patch.object(auto_schedules,"server_ids",return_value=["primary","secondary"]))
        for p in self.patches:p.start()
        from app.main import app
        self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test")

    async def asyncTearDown(self):
        await self.http.aclose()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup();await database.close_db();self.db_patch.stop()

    async def create(self,**values):
        r=await self.http.post("/api/v1/auto-schedules",json={"name":"All metrics","hour":0,"minute":0,"enabled":True,**values})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()["data"]["id"]

    async def task(self):
        return await self.pool.fetchrow("SELECT * FROM report_auto_tasks ORDER BY id LIMIT 1")

    async def test_api_validation_crud_and_default_disabled(self):
        r=await self.http.post("/api/v1/auto-schedules",json={"name":"Draft","hour":23,"minute":59})
        self.assertEqual(r.status_code,200,r.text);row=r.json()["data"];self.assertFalse(row["enabled"])
        for value in [{"hour":24},{"minute":60},{"timezone":"Bad/Zone"}]:
            r=await self.http.post("/api/v1/auto-schedules",json={"name":"Bad",**value});self.assertEqual(r.status_code,422)
        r=await self.http.put(f"/api/v1/auto-schedules/{row['id']}",json={"name":"Changed","hour":0,"minute":0})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()["data"]["hour"],0)
        r=await self.http.get("/api/v1/auto-schedules");self.assertEqual(r.json()["data"][0]["run_status"],"WAITING")
        r=await self.http.delete(f"/api/v1/auto-schedules/{row['id']}");self.assertEqual(r.status_code,200)
        r=await self.http.delete(f"/api/v1/auto-schedules/{row['id']}");self.assertEqual(r.status_code,404)

    async def test_dashboard_counts_both_manual_and_automatic_schedules(self):
        manual=await self.pool.fetchval("SELECT COUNT(*) FROM report_schedules")
        active=await self.pool.fetchval("SELECT COUNT(*) FROM report_schedules WHERE enabled")
        await self.create();await self.create(enabled=False)
        r=await self.http.get("/api/v1/dashboard/summary")
        self.assertEqual(r.json()["data"]["total_schedules"],manual+2)
        self.assertEqual(r.json()["data"]["active_schedules"],active+1)

    async def test_preview_for_all_sources_and_status_filter(self):
        from app.api.v1 import auto_schedules
        disabled={"hostid":"2","name":"Archived","status":"1"}
        with patch.object(auto_schedules,"inventory",AsyncMock(return_value=[("primary",[self.host,disabled],[disabled]),("secondary",[disabled],[disabled])])) as inventory:
            r=await self.http.get("/api/v1/auto-schedules/preview?zabbix_server=all&host_status=disabled")
            self.assertEqual(r.status_code,200,r.text);inventory.assert_awaited_once_with("all","disabled")
            self.assertEqual(r.json()["data"]["hosts"],2)
            self.assertEqual([s["disabled"] for s in r.json()["data"]["servers"]],[1,1])
        r=await self.http.get("/api/v1/auto-schedules/preview?host_status=invalid")
        self.assertEqual(r.status_code,422)

    async def test_all_numeric_metrics_split_without_truncation_resume_and_real_pdf(self):
        self.items.extend([{"itemid":"100","value_type":"1","status":"0"},{"itemid":"101","value_type":"3","status":"1"}])
        id=await self.create();run=await auto.enqueue_schedule(id);self.assertIsNotNone(run)
        self.assertTrue(await auto.process_one_task());t=await self.task()
        self.assertEqual((t["item_offset"],t["files_completed"],t["status"]),(20,1,"PENDING"))
        # Reloading database and reacquiring locks simulates a worker process restart.
        await database.close_db();await database.init_db();self.pool=database.get_pool()
        self.assertTrue(await auto.process_one_task());t=await self.task()
        self.assertEqual((t["item_offset"],t["files_completed"],t["status"]),(25,2,"SUCCESS"))
        self.assertEqual([c.args[1] for c in self.collect.await_args_list],[list(map(str,range(1,21))),list(map(str,range(21,26)))])
        self.assertEqual(self.client.get_items.await_count,1)
        logs=await self.pool.fetch("SELECT * FROM report_execution_logs ORDER BY id")
        self.assertEqual([r["auto_batch_index"] for r in logs],[1,2])
        self.assertEqual(len({r["report_filename"] for r in logs}),2)
        for row in logs:self.assertTrue((Path(self.temp.name)/row["report_filename"]).read_bytes().startswith(b"%PDF-"))
        self.assertFalse(await auto.process_one_task())

    async def test_all_sources_keep_duplicate_host_ids_and_enqueue_once(self):
        self.inventory.return_value=[("primary",[self.host],[self.host]),("secondary",[self.host],[self.host])]
        id=await self.create()
        runs=await asyncio.gather(auto.enqueue_schedule(id),auto.enqueue_schedule(id))
        self.assertEqual(sum(r is not None for r in runs),1)
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_tasks"),2)
        self.assertEqual(await self.pool.fetchval("SELECT report_date FROM report_auto_runs"),datetime.now(ZoneInfo("Asia/Jakarta")).date()-timedelta(days=1))

    async def test_pause_resume_and_delete_preserves_files_and_logs(self):
        id=await self.create();await auto.enqueue_schedule(id);await auto.process_one_task()
        await self.http.patch(f"/api/v1/auto-schedules/{id}/status",json={"enabled":False})
        self.assertFalse(await auto.process_one_task())
        r=await self.http.get("/api/v1/auto-schedules");self.assertEqual(r.json()["data"][0]["run_status"],"PAUSED")
        await self.http.patch(f"/api/v1/auto-schedules/{id}/status",json={"enabled":True});await auto.process_one_task()
        r=await self.http.get(f"/api/v1/auto-schedules/{id}/tasks?limit=1");self.assertEqual(r.json()["total"],1)
        self.assertEqual(r.json()["data"][0]["total_metrics"],25)
        await self.http.delete(f"/api/v1/auto-schedules/{id}")
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_execution_logs WHERE report_filename IS NOT NULL"),2)
        self.assertIsNone(await self.pool.fetchval("SELECT schedule_id FROM report_auto_runs"))

    async def test_concurrent_consumers_do_not_duplicate_batch(self):
        id=await self.create();await auto.enqueue_schedule(id)
        original=self.collect.side_effect
        async def delayed(*args):await asyncio.sleep(.15);return await original(*args)
        self.collect.side_effect=delayed
        await asyncio.gather(auto.process_one_task(),auto.process_one_task())
        self.assertEqual(self.collect.await_count,1);self.assertEqual((await self.task())["item_offset"],20)

    async def test_no_metrics_skipped_and_empty_batch_continues(self):
        id=await self.create();await auto.enqueue_schedule(id)
        async def empty_first(client,ids,start,end,resolution):
            return [{"item":{"name":id},"points":[],"warning":"Tidak ada data"} for id in ids] if ids[0]=="1" else [{"item":{"name":id},"points":[{"timestamp":start,"value":1}],"source":"history"} for id in ids]
        self.collect.side_effect=empty_first
        await auto.process_one_task();await auto.process_one_task()
        self.assertEqual((await self.task())["status"],"PARTIAL")
        self.assertEqual((await self.task())["item_offset"],25)
        self.assertEqual((await self.task())["files_completed"],1)
        await self.pool.execute("UPDATE report_auto_tasks SET status='PENDING',item_ids=NULL,item_offset=0,host_id='2'")
        await auto.process_one_task();self.assertEqual((await self.task())["status"],"SKIPPED")

    async def test_retry_limit_and_interrupted_log_recovery(self):
        id=await self.create();await auto.enqueue_schedule(id)
        self.items=self.items[:20]
        self.collect.side_effect=RuntimeError("upstream unavailable")
        for count in range(1,4):
            await auto.process_one_task();t=await self.task();self.assertEqual(t["attempts"],count if count<3 else 0)
            await self.pool.execute("UPDATE report_auto_tasks SET next_retry_at=NULL")
        self.assertEqual((await self.task())["status"],"FAILED")
        self.assertFalse(await auto.process_one_task())
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_execution_logs WHERE status='RUNNING'"),0)

    async def test_failed_part_does_not_block_remaining_metrics(self):
        id=await self.create();await auto.enqueue_schedule(id)
        original=self.collect.side_effect;self.collect.side_effect=RuntimeError("PDF processing failed")
        for _ in range(3):
            await auto.process_one_task();await self.pool.execute("UPDATE report_auto_tasks SET next_retry_at=NULL")
        t=await self.task();self.assertEqual((t["item_offset"],t["status"]),(20,"PENDING"))
        self.collect.side_effect=original;await auto.process_one_task();t=await self.task()
        self.assertEqual((t["item_offset"],t["files_completed"],t["status"]),(25,1,"PARTIAL"))

    async def test_item_discovery_failure_retries_then_fails_without_pdf(self):
        id=await self.create();await auto.enqueue_schedule(id)
        self.client.get_items.side_effect=RuntimeError("Cannot discover items")
        for _ in range(3):
            await auto.process_one_task();await self.pool.execute("UPDATE report_auto_tasks SET next_retry_at=NULL")
        self.assertEqual((await self.task())["status"],"FAILED")
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_execution_logs"),0)

    async def test_stale_running_task_recovered(self):
        id=await self.create();await auto.enqueue_schedule(id);t=await self.task()
        await self.pool.execute("UPDATE report_auto_tasks SET status='RUNNING'")
        await self.pool.execute("INSERT INTO report_execution_logs(status,auto_task_id) VALUES('RUNNING',$1)",t["id"])
        await auto.process_one_task()
        self.assertEqual(await self.pool.fetchval("SELECT status FROM report_execution_logs ORDER BY id LIMIT 1"),"FAILED")
        self.assertEqual((await self.task())["item_offset"],20)

    async def test_enqueue_failure_records_retry_without_advancing_date(self):
        id=await self.create();self.inventory.return_value=[]
        self.assertIsNone(await auto.enqueue_schedule(id))
        row=await self.pool.fetchrow("SELECT * FROM report_auto_schedules WHERE id=$1",id)
        self.assertIsNotNone(row["last_error"]);self.assertIsNotNone(row["next_retry_at"]);self.assertIsNone(row["last_enqueued_date"])

    async def test_backlog_limit_and_max_active_policies(self):
        id=await self.create()
        today=datetime.now(ZoneInfo("Asia/Jakarta")).date()
        await self.pool.execute("UPDATE report_auto_schedules SET last_enqueued_date=$1 WHERE id=$2",today-timedelta(days=8),id)
        for _ in range(7):self.assertIsNotNone(await auto.enqueue_schedule(id))
        self.assertIsNone(await auto.enqueue_schedule(id))
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_runs"),7)
        self.assertIn("tujuh",await self.pool.fetchval("SELECT last_error FROM report_auto_schedules WHERE id=$1",id))
        for _ in range(9):await self.create()
        r=await self.http.post("/api/v1/auto-schedules",json={"name":"Too many","enabled":True})
        self.assertEqual(r.status_code,400)
