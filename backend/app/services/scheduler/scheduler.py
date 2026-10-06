import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import (
    close_db,
    decode_item_ids,
    get_pool,
    init_db,
)
from app.services.report.pdf import (
    generate_multi_item_pdf,
)
from app.services.zabbix.client import (
    ZabbixClient,
)

async def run_schedule(schedule):
    schedule_id = schedule["id"]

    timezone = ZoneInfo(
        schedule["timezone"]
    )

    now = datetime.now(timezone)

    scheduled_today = now.replace(
        hour=schedule["hour"],
        minute=schedule["minute"],
        second=0,
        microsecond=0,
    )

    if now < scheduled_today:
        return

    today = now.date()

    if schedule["last_run_date"] == today:
        return

    pool = get_pool()

    # Catat awal eksekusi
    execution_id = await pool.fetchval(
        """
        INSERT INTO report_execution_logs (
            schedule_id,
            started_at,
            status
        )
        VALUES ($1, $2, 'RUNNING')
        RETURNING id;
        """,
        schedule_id,
        now,
    )

    print(
        f"Running schedule {schedule_id}: "
        f"{schedule['name']}"
    )

    try:
        yesterday = now - timedelta(days=1)

        start = datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            0,
            0,
            0,
            tzinfo=timezone,
        )

        end = datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            23,
            59,
            59,
            tzinfo=timezone,
        )

        time_from = int(start.timestamp())
        time_till = int(end.timestamp())

        client = ZabbixClient()

        item_data_list = []

        item_ids = decode_item_ids(
            schedule["item_ids"]
        )

        for item_id in item_ids:
            try:
                result = await client.get_item_data(
                    itemid=str(item_id),
                    time_from=time_from,
                    time_till=time_till,
                )

                item_data_list.append(result)

            except Exception as exc:
                print(
                    f"Item {item_id} failed: {exc}"
                )

        # Semua item gagal / tidak ada data
        if not item_data_list:
            error_message = (
                "No data available for scheduled report."
            )

            await pool.execute(
                """
                UPDATE report_execution_logs
                SET
                    finished_at = NOW(),
                    status = 'FAILED',
                    error_message = $1
                WHERE id = $2;
                """,
                error_message,
                execution_id,
            )

            print(
                f"Schedule {schedule_id}: "
                "no data available."
            )

            return

        # Generate PDF
        try:
            pdf_path = generate_multi_item_pdf(
                host_name=schedule["host_name"],
                item_data_list=item_data_list,
                time_from=time_from,
                time_till=time_till,
                title=schedule["name"],
            )

            print(
                f"Generated: {pdf_path}"
            )

        except Exception as exc:
            error_message = str(exc)

            await pool.execute(
                """
                UPDATE report_execution_logs
                SET
                    finished_at = NOW(),
                    status = 'FAILED',
                    error_message = $1
                WHERE id = $2;
                """,
                error_message,
                execution_id,
            )

            print(
                f"PDF generation failed: {exc}"
            )

            return

        # Ambil nama file PDF
        report_filename = str(
            pdf_path
        ).replace("\\", "/").split("/")[-1]

        # Tandai schedule sudah berhasil dijalankan
        await pool.execute(
            """
            UPDATE report_schedules
            SET
                last_run_date = $1,
                updated_at = NOW()
            WHERE id = $2;
            """,
            today,
            schedule_id,
        )

        # Catat eksekusi berhasil
        await pool.execute(
            """
            UPDATE report_execution_logs
            SET
                finished_at = NOW(),
                status = 'SUCCESS',
                report_filename = $1
            WHERE id = $2;
            """,
            report_filename,
            execution_id,
        )

        print(
            f"Schedule {schedule_id} "
            f"completed for {today}."
        )

    except Exception as exc:
        error_message = str(exc)

        await pool.execute(
            """
            UPDATE report_execution_logs
            SET
                finished_at = NOW(),
                status = 'FAILED',
                error_message = $1
            WHERE id = $2;
            """,
            error_message,
            execution_id,
        )

        print(
            f"Schedule {schedule_id} failed: "
            f"{exc}"
        )

async def process_schedules():
    pool = get_pool()

    rows = await pool.fetch(
        """
        SELECT
            id,
            name,
            host_id,
            host_name,
            item_ids,
            hour,
            minute,
            timezone,
            enabled,
            last_run_date
        FROM report_schedules
        WHERE enabled = TRUE
        ORDER BY id;
        """
    )

    for row in rows:
        try:
            await run_schedule(row)

        except Exception as exc:
            print(
                f"Schedule {row['id']} failed: "
                f"{exc}"
            )


async def main():
    await init_db()

    scheduler = AsyncIOScheduler(
        timezone="Asia/Jakarta"
    )

    scheduler.add_job(
        process_schedules,
        "interval",
        seconds=30,
        id="schedule_poller",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()

    print(
        "Database-backed report scheduler started."
    )

    try:
        while True:
            await asyncio.sleep(3600)

    finally:
        scheduler.shutdown()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())