import asyncio
import logging
from contextlib import suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import close_db, get_pool, init_db
from app.services.scheduler.heartbeat import SchedulerHeartbeat
from app.services.scheduler.jobs import LOCK_NAMESPACE, run_schedule
from app.services.scheduler.auto import enqueue_due_schedules, worker_loop
from app.services.report.archive import archive_completed_runs

logger = logging.getLogger(__name__)
heartbeat = SchedulerHeartbeat()


async def process_schedules():
    try:
        # Manual requests have a bounded lifetime; schedule locks protect live jobs.
        await get_pool().execute("""
            UPDATE report_execution_logs SET status='FAILED', finished_at=NOW(),
                error_message='Eksekusi terputus atau melewati batas waktu.'
            WHERE status='RUNNING'
                AND auto_task_id IS NULL
                AND started_at < NOW()-($1::int * INTERVAL '1 second')
                AND (schedule_id IS NULL
                     OR pg_try_advisory_xact_lock($2::int, schedule_id))
        """, settings.REPORT_TIMEOUT_SECONDS+60, LOCK_NAMESPACE)
        rows = await get_pool().fetch("SELECT * FROM report_schedules WHERE enabled=TRUE ORDER BY id")
        for row in rows:
            try:
                await run_schedule(row)
            except Exception:
                logger.exception("Schedule %s failed", row["id"])
        # Completed PARTIAL reports also keep warnings in last_error. Only a
        # failed run waiting for retry should mark the scheduler unhealthy.
        failed = await get_pool().fetchval(
            "SELECT COUNT(*) FROM report_schedules WHERE enabled=TRUE AND last_error IS NOT NULL AND next_retry_at IS NOT NULL"
        )
        heartbeat.status = "error" if failed else "running"
    except Exception:
        heartbeat.status = "error"
        logger.exception("Schedule poll failed")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await init_db()
    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(process_schedules, "interval", seconds=30, id="schedule_poller",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()
    scheduler.add_job(enqueue_due_schedules, "interval", seconds=30, id="automatic_schedule_enqueuer",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(archive_completed_runs, "interval", seconds=30, id="automatic_archive_packager",
                      replace_existing=True, max_instances=1, coalesce=True)
    automatic_workers = [asyncio.create_task(worker_loop()) for _ in range(settings.AUTO_REPORT_WORKERS)]
    heartbeat_task = asyncio.create_task(heartbeat.run())
    logger.info("Database-backed report scheduler started.")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown()
        for worker in automatic_workers:
            worker.cancel()
        await asyncio.gather(*automatic_workers, return_exceptions=True)
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
