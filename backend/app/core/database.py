import json
import os

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://", 1)
pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    if pool is not None:
        return
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL belum dikonfigurasi.")
    new_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8, command_timeout=30)
    try:
        async with new_pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(20261006);")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS report_schedules (
                    id SERIAL PRIMARY KEY, name TEXT NOT NULL, host_id TEXT,
                    host_name TEXT NOT NULL, item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
                    minute SMALLINT NOT NULL CHECK (minute BETWEEN 0 AND 59),
                    timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    last_run_date DATE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS report_execution_logs (
                    id SERIAL PRIMARY KEY, schedule_id INTEGER,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ,
                    status VARCHAR(20) NOT NULL, report_filename TEXT, error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                ALTER TABLE report_schedules ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;
                ALTER TABLE report_schedules ADD COLUMN IF NOT EXISTS last_error TEXT;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS schedule_name TEXT;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS host_name TEXT;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS trigger_type TEXT DEFAULT 'scheduled';
                CREATE INDEX IF NOT EXISTS execution_logs_started_idx
                    ON report_execution_logs (started_at DESC);
            """)
    except BaseException:
        await new_pool.close()
        raise
    pool = new_pool


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None


def get_pool():
    if pool is None:
        raise RuntimeError("Database pool belum diinisialisasi.")
    return pool


def decode_item_ids(value):
    if value is None:
        return []
    return json.loads(value) if isinstance(value, str) else list(value)
