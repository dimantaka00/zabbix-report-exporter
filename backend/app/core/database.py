import json
import os

import asyncpg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
).replace(
    "postgresql+asyncpg://",
    "postgresql://",
    1,
)


pool: asyncpg.Pool | None = None


async def init_db():
    global pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL belum dikonfigurasi."
        )

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
    )

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_schedules (
                id SERIAL PRIMARY KEY,

                name TEXT NOT NULL,

                host_id TEXT,

                host_name TEXT NOT NULL,

                item_ids JSONB NOT NULL
                    DEFAULT '[]'::jsonb,

                hour SMALLINT NOT NULL
                    CHECK (hour >= 0 AND hour <= 23),

                minute SMALLINT NOT NULL
                    CHECK (minute >= 0 AND minute <= 59),

                timezone TEXT NOT NULL
                    DEFAULT 'Asia/Jakarta',

                enabled BOOLEAN NOT NULL
                    DEFAULT TRUE,

                last_run_date DATE,

                created_at TIMESTAMPTZ NOT NULL
                    DEFAULT NOW(),

                updated_at TIMESTAMPTZ NOT NULL
                    DEFAULT NOW()
            );
            """
        )


async def close_db():
    global pool

    if pool:
        await pool.close()
        pool = None


def get_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError(
            "Database pool belum diinisialisasi."
        )

    return pool


def decode_item_ids(value):
    if value is None:
        return []

    if isinstance(value, str):
        return json.loads(value)

    return list(value)