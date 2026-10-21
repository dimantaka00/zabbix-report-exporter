import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from app.api.v1 import auto_schedules, dashboard, reports
from app.models.requests import AutoScheduleCreate
from app.services.report import archive
from app.services.scheduler import auto
from pydantic import ValidationError
import test_auto_schedules as baseline


class SelectionValidationTests(unittest.TestCase):
    def test_rejects_empty_duplicate_and_mismatched_selections(self):
        selected={"zabbix_server":"primary","host_id":"1","item_ids":["2"]}
        for change in [{"host_selections":[]},{"host_selections":[selected,selected]},
            {"host_selections":[{**selected,"item_ids":[]}]},{"host_selections":[{**selected,"item_ids":["2","2"]}]},
            {"host_selections":[{**selected,"host_id":"../1"}]},{"zabbix_server":"secondary"},
            {"selection_mode":"all"}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                AutoScheduleCreate(**{"name":"Selected","selection_mode":"selected","host_selections":[selected],**change})
        self.assertEqual(len(AutoScheduleCreate(name="Many metrics",selection_mode="selected",host_selections=[{**selected,"item_ids":list(map(str,range(1,26)))}]).host_selections[0].item_ids),25)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"),"Requires disposable PostgreSQL")
class SelectedArchiveTests(unittest.IsolatedAsyncioTestCase):
    create=baseline.AutoQueueTests.create
    task=baseline.AutoQueueTests.task

    async def asyncSetUp(self):
        await baseline.AutoQueueTests.asyncSetUp(self)
        self.patches.extend([patch.object(archive,"REPORT_DIR",Path(self.temp.name)),
            patch.object(reports,"REPORT_DIR",Path(self.temp.name)),patch.object(dashboard,"REPORT_DIR",Path(self.temp.name)),
            patch.object(auto_schedules,"inventory",self.inventory),patch.object(auto_schedules,"ZabbixClient",return_value=self.client)])
        for p in self.patches[-5:]:p.start()

    async def asyncTearDown(self):
        await baseline.AutoQueueTests.asyncTearDown(self)

    async def selected(self,ids=None,**change):
        return await self.create(selection_mode="selected",host_selections=[{"zabbix_server":"primary","host_id":"1","item_ids":ids}],**change)

    async def completed(self,**change):
        id=await self.create(**change);run=await auto.enqueue_schedule(id)
        while await auto.process_one_task():pass
        return run

    async def test_selected_hosts_and_metrics_are_persisted_and_used(self):
        other={"hostid":"2","name":"Other","status":"0"}
        self.inventory.return_value=[("primary",[self.host,other],[self.host,other])]
        id=await self.selected(["2","25"]);run=await auto.enqueue_schedule(id)
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_tasks"),1)
        await auto.process_one_task();self.assertEqual(self.collect.await_args.args[1],["2","25"])
        r=await self.http.get("/api/v1/auto-schedules");self.assertEqual(r.json()["data"][0]["host_selections"][0]["item_ids"],["2","25"])
        r=await self.http.put(f"/api/v1/auto-schedules/{id}",json={"name":"Changed","selection_mode":"selected","host_selections":[{"zabbix_server":"primary","host_id":"1","item_ids":["1"]}],"package_zip":False})
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(await self.pool.fetchval("SELECT package_zip FROM report_auto_runs WHERE id=$1",run))
        self.assertEqual(r.json()["data"]["host_selections"][0]["item_ids"],["1"])

    async def test_api_rejects_other_host_text_and_inactive_metrics(self):
        self.items.extend([{"itemid":"100","value_type":"1","status":"0"},{"itemid":"101","value_type":"0","status":"1"}])
        for host,ids in [("999",None),("1",["999"]),("1",["100"]),("1",["101"])]:
            r=await self.http.post("/api/v1/auto-schedules",json={"name":"Invalid","selection_mode":"selected","host_selections":[{"zabbix_server":"primary","host_id":host,"item_ids":ids}]})
            self.assertEqual(r.status_code,400,r.text)

    async def test_explicit_selection_over_twenty_metrics_is_split_then_zipped(self):
        id=await self.selected(list(map(str,range(1,26))));run=await auto.enqueue_schedule(id)
        while await auto.process_one_task():pass
        self.assertEqual([len(c.args[1]) for c in self.collect.await_args_list],[20,5])
        self.assertTrue(await archive.archive_run(run))
        self.assertEqual((await self.task())["item_offset"],25)

    async def test_manual_pdf_is_preserved_when_automatic_pdfs_are_cleaned(self):
        run=await self.completed();manual=Path(self.temp.name)/"manual.pdf";manual.write_bytes(b'%PDF-1.4 manually saved')
        self.assertTrue(await archive.archive_run(run));self.assertEqual(manual.read_bytes(),b'%PDF-1.4 manually saved')
        self.assertEqual(list(Path(self.temp.name).glob("*.pdf")),[manual])

    async def test_inactive_selection_at_execution_marks_partial(self):
        id=await self.selected(["1","2"])
        self.items[1]["status"]="1"
        await auto.enqueue_schedule(id);await auto.process_one_task()
        self.assertEqual(self.collect.await_args.args[1],["1"])
        self.assertEqual((await self.task())["status"],"PARTIAL")
        self.assertIn("2",await self.pool.fetchval("SELECT error_message FROM report_execution_logs"))

    async def test_missing_selected_host_does_not_silently_expand_scope(self):
        id=await self.selected(["1"]);self.inventory.return_value=[]
        self.assertIsNone(await auto.enqueue_schedule(id))
        self.assertEqual(await self.pool.fetchval("SELECT COUNT(*) FROM report_auto_tasks"),0)
        self.assertIsNone(await self.pool.fetchval("SELECT last_enqueued_date FROM report_auto_schedules WHERE id=$1",id))

    async def test_two_servers_with_same_host_id_use_distinct_metric_selections(self):
        self.inventory.return_value=[("primary",[self.host],[self.host]),("secondary",[self.host],[self.host])]
        id=await self.create(selection_mode="selected",host_selections=[{"zabbix_server":"primary","host_id":"1","item_ids":["1"]},{"zabbix_server":"secondary","host_id":"1","item_ids":["2"]}])
        run=await auto.enqueue_schedule(id)
        while await auto.process_one_task():pass
        self.assertEqual([c.args[1] for c in self.collect.await_args_list],[["1"],["2"]])
        self.assertTrue(await archive.archive_run(run))
        self.assertEqual(len(list(Path(self.temp.name).glob("*.zip"))),1)
        with ZipFile(next(Path(self.temp.name).glob("*.zip"))) as zipped:
            self.assertEqual(len([n for n in zipped.namelist() if n.endswith('.pdf')]),2)

    async def test_zip_verified_originals_removed_and_pdf_downloads_stream_without_disk_copy(self):
        run=await self.completed()
        originals={p.name:p.read_bytes() for p in Path(self.temp.name).glob("*.pdf")}
        self.assertEqual(len(originals),2)
        results=await asyncio.gather(archive.archive_run(run),archive.archive_run(run))
        self.assertEqual(sum(results),1)
        row=await self.pool.fetchrow("SELECT * FROM report_auto_runs WHERE id=$1",run)
        self.assertEqual(row["archive_status"],"READY");self.assertTrue(row["archive_cleanup_done"])
        self.assertEqual(row["original_size"],sum(map(len,originals.values())))
        self.assertFalse(list(Path(self.temp.name).glob("*.pdf")))
        path=Path(self.temp.name)/row["archive_filename"]
        with ZipFile(path) as zipped:
            self.assertIsNone(zipped.testzip())
            self.assertEqual(len(json.loads(zipped.read("manifest.json"))["files"]),2)
            for name,data in originals.items():self.assertEqual(zipped.read(name),data)
        r=await self.http.get(f"/api/v1/reports/{path.name}");self.assertEqual(r.status_code,200);self.assertEqual(r.content,path.read_bytes())
        for name,data in originals.items():
            for url in [f"/api/v1/reports/{name}",f"/api/v1/reports/archives/{path.name}/{name}"]:
                r=await self.http.get(url);self.assertEqual(r.status_code,200,r.text[:100]);self.assertEqual(r.content,data)
        self.assertFalse(list(Path(self.temp.name).glob("*.pdf")))
        r=await self.http.get("/api/v1/reports");self.assertEqual(r.json()["total"],1);self.assertEqual(r.json()["data"][0]["filename"],path.name)
        r=await self.http.get("/api/v1/history");self.assertTrue(all(h["archive_filename"]==path.name for h in r.json()["data"]))
        r=await self.http.get("/api/v1/auto-schedules");self.assertEqual(r.json()["data"][0]["archive_download_url"],f"/api/v1/reports/{path.name}")
        r=await self.http.get("/api/v1/dashboard/summary");self.assertEqual(r.json()["data"]["total_reports"],1)

    async def test_zip_waits_for_all_parts_and_disabled_packaging_preserves_pdfs(self):
        id=await self.create(package_zip=False);run=await auto.enqueue_schedule(id);await auto.process_one_task()
        self.assertFalse(await archive.archive_run(run))
        await auto.process_one_task();self.assertFalse(await archive.archive_run(run))
        self.assertEqual(len(list(Path(self.temp.name).glob("*.pdf"))),2)
        self.assertFalse(list(Path(self.temp.name).glob("*.zip")))
        # Opt-in is stored per run, independently of future policy updates.
        await self.pool.execute("UPDATE report_auto_runs SET package_zip=TRUE,archive_status='PENDING' WHERE id=$1",run)
        await self.pool.execute("UPDATE report_auto_tasks SET status='PENDING' WHERE run_id=$1",run)
        self.assertFalse(await archive.archive_run(run))

    async def test_missing_pdf_preserves_remaining_files_and_retries(self):
        run=await self.completed();pdfs=list(Path(self.temp.name).glob("*.pdf"));missing=pdfs[0];saved=missing.read_bytes();missing.unlink()
        self.assertFalse(await archive.archive_run(run));self.assertTrue(pdfs[1].exists())
        self.assertEqual(await self.pool.fetchval("SELECT archive_status FROM report_auto_runs WHERE id=$1",run),"ERROR")
        self.assertFalse(list(Path(self.temp.name).glob("*.tmp")))
        missing.write_bytes(saved)
        await archive.archive_completed_runs()  # Retry deadline must be honored by the poller.
        self.assertTrue(missing.exists())
        await self.pool.execute("UPDATE report_auto_runs SET archive_next_retry_at=NULL WHERE id=$1",run)
        await archive.archive_completed_runs();self.assertFalse(missing.exists())

    async def test_restart_after_ready_recovers_cleanup_without_repacking(self):
        run=await self.completed()
        with patch.object(archive,"cleanup_pdfs",side_effect=OSError("cleanup interrupted")):
            self.assertFalse(await archive.archive_run(run))
        row=await self.pool.fetchrow("SELECT * FROM report_auto_runs WHERE id=$1",run)
        self.assertEqual(row["archive_status"],"READY");self.assertFalse(row["archive_cleanup_done"])
        self.assertEqual(len(list(Path(self.temp.name).glob("*.pdf"))),2)
        with patch.object(archive,"build_archive",side_effect=AssertionError("must not rebuild")):
            self.assertTrue(await archive.archive_run(run))
        self.assertFalse(list(Path(self.temp.name).glob("*.pdf")))

    async def test_corrupt_zip_and_changed_pdf_never_delete_originals(self):
        run=await self.completed()
        with patch.object(archive,"cleanup_pdfs",side_effect=OSError("cleanup interrupted")):
            await archive.archive_run(run)
        row=await self.pool.fetchrow("SELECT * FROM report_auto_runs WHERE id=$1",run)
        path=Path(self.temp.name)/row["archive_filename"];saved=path.read_bytes();path.write_bytes(b'broken ZIP')
        self.assertFalse(await archive.archive_run(run));self.assertEqual(len(list(Path(self.temp.name).glob("*.pdf"))),2)
        path.write_bytes(saved)
        source=next(Path(self.temp.name).glob("*.pdf"));source.write_bytes(b'PDF modified outside packaging')
        self.assertFalse(await archive.archive_run(run));self.assertEqual(len(list(Path(self.temp.name).glob("*.pdf"))),2)

    async def test_empty_period_and_deleted_policy(self):
        id=await self.create();run=await auto.enqueue_schedule(id);self.items=[]
        await auto.process_one_task();self.assertTrue(await archive.archive_run(run))
        self.assertEqual(await self.pool.fetchval("SELECT archive_status FROM report_auto_runs WHERE id=$1",run),"EMPTY")
        self.assertFalse(list(Path(self.temp.name).glob("*.zip")))
        await self.pool.execute("TRUNCATE report_auto_tasks,report_auto_runs,report_auto_schedules,report_execution_logs RESTART IDENTITY CASCADE")
        self.items=[{"itemid":"1","name":"Metric","value_type":"0","status":"0","units":"%"}]
        run=await self.completed();await self.http.delete("/api/v1/auto-schedules/1")
        self.assertTrue(await archive.archive_run(run))
        self.assertEqual(len(list(Path(self.temp.name).glob("*.zip"))),1)

    async def test_paths_and_unregistered_members_are_rejected(self):
        for name in ["../secret.pdf","..\\secret.pdf","/secret.pdf","bad\n.pdf"]:
            with self.subTest(name=name),self.assertRaises(ValueError):archive.report_path(name,".pdf")
        run=await self.completed();await archive.archive_run(run)
        name=await self.pool.fetchval("SELECT archive_filename FROM report_auto_runs WHERE id=$1",run)
        r=await self.http.get(f"/api/v1/reports/archives/{name}/secret.pdf");self.assertEqual(r.status_code,404)
        r=await self.http.get(f"/api/v1/reports/archives/{name}/bad.txt");self.assertEqual(r.status_code,400)

    async def test_existing_policy_defaults_do_not_opt_into_cleanup(self):
        row=await self.pool.fetchrow("""INSERT INTO report_auto_schedules(name,zabbix_server,host_status,hour,minute,timezone)
            VALUES('Existing','all','all',0,0,'Asia/Jakarta') RETURNING *""")
        self.assertFalse(row["package_zip"]);self.assertEqual(row["selection_mode"],"all")

    async def test_backup_lock_defers_packaging_and_pdf_deletion(self):
        run=await self.completed()
        async with self.pool.acquire() as conn:
            await conn.fetchval("SELECT pg_advisory_lock($1,0)",archive.BACKUP_GUARD_LOCK)
            try:
                self.assertFalse(await archive.archive_run(run))
                self.assertEqual(len(list(Path(self.temp.name).glob("*.pdf"))),2)
                self.assertFalse(list(Path(self.temp.name).glob("*.zip")))
            finally:
                await conn.fetchval("SELECT pg_advisory_unlock($1,0)",archive.BACKUP_GUARD_LOCK)
        self.assertTrue(await archive.archive_run(run))
        self.assertFalse(list(Path(self.temp.name).glob("*.pdf")))
