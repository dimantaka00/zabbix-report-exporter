import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError
from app.api.v1 import dashboard, reports, schedules
from app.core import database
from app.models.requests import ScheduleCreate, GenerateReportRequest
from app.services.scheduler import scheduler, jobs
from app.services.scheduler.heartbeat import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, SchedulerHeartbeat
from app.services.report import pdf
from app.services.report.data import summarize_points
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

    def test_constant_and_weighted_statistics(self):
        self.assertEqual(summarize_points([{"value":1},{"value":1}]),
                         {"minimum":1,"maximum":1,"average":1,"samples":2})
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
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    def test_pdf_failure_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pdf,"REPORT_DIR",Path(folder)), \
             patch.object(pdf.SimpleDocTemplate,"build",side_effect=RuntimeError("render")):
            with self.assertRaises(RuntimeError):
                pdf.generate_multi_item_pdf("Host",[DATA],1,100)
            self.assertEqual(list(Path(folder).iterdir()),[])


class ZabbixDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client=ZabbixClient.__new__(ZabbixClient)
        self.client.call=AsyncMock(side_effect=[[HOST],[ITEM]])

    async def test_metric_must_belong_to_host(self):
        self.client.call.side_effect=[[HOST],[{**ITEM,"hostid":"2"}]]
        with self.assertRaisesRegex(ValueError,"host"):
            await self.client.validate_selection("1","ignored",["10"])

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
        self.assertAlmostEqual(result["summary"]["average"],40/11)

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
        self.zabbix = MagicMock(get_hosts=AsyncMock(return_value=[]))
        for target, value in (
            ("get_pool", MagicMock(return_value=self.pool)),
            ("create_redis_client", MagicMock(return_value=self.redis)),
            ("ZabbixClient", MagicMock(return_value=self.zabbix)),
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
        self.assertEqual(self.redis.aclose.await_count, 5)

    async def test_redis_error_is_unknown_and_connection_is_closed(self):
        self.redis.ping.side_effect = RuntimeError("Redis unavailable")
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
        fake_zabbix = MagicMock(get_hosts=AsyncMock(return_value=[]))
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
        self.temp=tempfile.TemporaryDirectory()
        self.client=MagicMock(validate_selection=AsyncMock(return_value=HOST),
                              get_item_data=AsyncMock(return_value=DATA))
        self.patches=[patch.object(module,"ZabbixClient",return_value=self.client) for module in (jobs,reports,schedules)]
        self.patches += [patch.object(module,"REPORT_DIR",Path(self.temp.name)) for module in (reports,pdf)]
        for p in self.patches:p.start()
        from app.main import app
        self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test")

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
        async def data(id,*_):
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
        async def slow(*_):
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
        async def slow(*_):
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
        history=(await self.http.get("/api/v1/history?limit=1")).json()
        self.assertEqual(history["total"],1)
        self.assertEqual(history["data"][0]["host_name"],"Test host")
        self.assertEqual(history["data"][0]["trigger_type"],"manual_report")
        archive=(await self.http.get("/api/v1/reports?limit=1")).json()
        self.assertEqual(archive["total"],1)
        self.assertEqual((await self.http.get(archive["data"][0]["download_url"])).content,response.content)
        self.assertEqual((await self.http.get("/api/v1/history?offset=1")).json()["data"],[])

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

    async def test_readiness_endpoint_checks_database(self):
        self.assertEqual((await self.http.get("/health/ready")).status_code,200)

    async def test_interrupted_manual_report_eventually_expires_without_touching_recent_request(self):
        entered=asyncio.Event()
        async def slow(*_):
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
