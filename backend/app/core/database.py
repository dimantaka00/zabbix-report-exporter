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
                    zabbix_server TEXT NOT NULL DEFAULT 'primary',
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
                ALTER TABLE report_schedules ADD COLUMN IF NOT EXISTS zabbix_server TEXT NOT NULL DEFAULT 'primary';
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS schedule_name TEXT;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS host_name TEXT;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS trigger_type TEXT DEFAULT 'scheduled';
                CREATE INDEX IF NOT EXISTS execution_logs_started_idx
                    ON report_execution_logs (started_at DESC);
                CREATE TABLE IF NOT EXISTS app_users (
                    id SERIAL PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL,
                    display_name VARCHAR(100) NOT NULL, password_hash TEXT NOT NULL,
                    role VARCHAR(16) NOT NULL CHECK(role IN ('admin','operator')),
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS app_sessions (
                    id BIGSERIAL PRIMARY KEY, token_hash CHAR(64) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                    csrf_token VARCHAR(64) NOT NULL, ip VARCHAR(45) NOT NULL,
                    country_code VARCHAR(2), country_name VARCHAR(100), ip_kind VARCHAR(32) NOT NULL,
                    user_agent VARCHAR(512) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_events (
                    id BIGSERIAL PRIMARY KEY, occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    user_id INTEGER, username VARCHAR(64), event_type VARCHAR(32) NOT NULL,
                    ip VARCHAR(45) NOT NULL, country_code VARCHAR(2), country_name VARCHAR(100),
                    ip_kind VARCHAR(32) NOT NULL, user_agent VARCHAR(512) NOT NULL,
                    method VARCHAR(16) NOT NULL, path VARCHAR(256) NOT NULL,
                    status_code INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS access_events_time_idx ON access_events(occurred_at DESC,id DESC);
                CREATE INDEX IF NOT EXISTS access_events_login_idx
                    ON access_events(ip,occurred_at DESC) WHERE event_type='login_failed';
                CREATE INDEX IF NOT EXISTS app_sessions_expiry_idx ON app_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS report_auto_schedules (
                    id SERIAL PRIMARY KEY, name TEXT NOT NULL,
                    zabbix_server TEXT NOT NULL CHECK(zabbix_server IN ('primary','secondary','all')),
                    host_status TEXT NOT NULL CHECK(host_status IN ('all','enabled','disabled')),
                    hour SMALLINT NOT NULL CHECK(hour BETWEEN 0 AND 23),
                    minute SMALLINT NOT NULL CHECK(minute BETWEEN 0 AND 59), timezone TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT FALSE, last_enqueued_date DATE,
                    next_retry_at TIMESTAMPTZ, last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS report_auto_runs (
                    id SERIAL PRIMARY KEY, schedule_id INTEGER REFERENCES report_auto_schedules(id) ON DELETE SET NULL,
                    schedule_name TEXT NOT NULL, timezone TEXT NOT NULL,
                    execution_date DATE NOT NULL, report_date DATE NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(schedule_id,execution_date)
                );
                CREATE TABLE IF NOT EXISTS report_auto_tasks (
                    id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES report_auto_runs(id) ON DELETE CASCADE,
                    zabbix_server TEXT NOT NULL CHECK(zabbix_server IN ('primary','secondary')),
                    host_id TEXT NOT NULL, host_name TEXT NOT NULL, item_ids JSONB,
                    item_offset INTEGER NOT NULL DEFAULT 0, files_completed INTEGER NOT NULL DEFAULT 0,
                    batches_failed INTEGER NOT NULL DEFAULT 0, has_warnings BOOLEAN NOT NULL DEFAULT FALSE,
                    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                        CHECK(status IN ('PENDING','RUNNING','SUCCESS','PARTIAL','FAILED','SKIPPED')),
                    attempts INTEGER NOT NULL DEFAULT 0, next_retry_at TIMESTAMPTZ, last_error TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(run_id,zabbix_server,host_id)
                );
                CREATE INDEX IF NOT EXISTS report_auto_tasks_queue_idx ON report_auto_tasks(status,next_retry_at,id);
                CREATE INDEX IF NOT EXISTS report_auto_tasks_run_idx ON report_auto_tasks(run_id);
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS auto_task_id INTEGER;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS auto_batch_index INTEGER;
                CREATE INDEX IF NOT EXISTS execution_logs_auto_task_idx ON report_execution_logs(auto_task_id);
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS selection_mode TEXT NOT NULL DEFAULT 'all';
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS host_selections JSONB NOT NULL DEFAULT '[]'::jsonb;
                -- Existing policies and periods retain their original PDF storage behavior.
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS package_zip BOOLEAN NOT NULL DEFAULT FALSE;
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS data_start_time TEXT NOT NULL DEFAULT '00:00';
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS data_end_time TEXT NOT NULL DEFAULT '23:59';
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS date_start DATE;
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS date_end DATE;
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS host_categories JSONB NOT NULL DEFAULT '[]'::jsonb;
                ALTER TABLE report_auto_schedules ADD COLUMN IF NOT EXISTS host_groups JSONB NOT NULL DEFAULT '[]'::jsonb;
                ALTER TABLE report_auto_tasks ADD COLUMN IF NOT EXISTS selected_item_ids JSONB;
                ALTER TABLE report_auto_tasks ADD COLUMN IF NOT EXISTS selection_warning TEXT;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS package_zip BOOLEAN NOT NULL DEFAULT FALSE;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS data_start_time TEXT NOT NULL DEFAULT '00:00';
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS data_end_time TEXT NOT NULL DEFAULT '23:59';
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_status TEXT NOT NULL DEFAULT 'NONE';
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_filename TEXT;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_size BIGINT;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS original_size BIGINT;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_error TEXT;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_next_retry_at TIMESTAMPTZ;
                ALTER TABLE report_auto_runs ADD COLUMN IF NOT EXISTS archive_cleanup_done BOOLEAN NOT NULL DEFAULT FALSE;
                ALTER TABLE report_execution_logs ADD COLUMN IF NOT EXISTS archive_filename TEXT;
                CREATE INDEX IF NOT EXISTS report_execution_logs_filename_idx ON report_execution_logs(report_filename)
                    WHERE report_filename IS NOT NULL;
                CREATE INDEX IF NOT EXISTS report_auto_runs_archive_idx ON report_auto_runs(archive_status,archive_next_retry_at)
                    WHERE package_zip;
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
