"""Short-lived worker status shared with the API through Redis."""

import asyncio
import logging
from pathlib import Path
from tempfile import gettempdir

import redis.asyncio as redis

from app.core.config import settings


HEARTBEAT_FILE = Path(gettempdir()) / "zabbix-scheduler-heartbeat"
HEARTBEAT_KEY = "zabbix-report-exporter:scheduler:heartbeat"
HEARTBEAT_INTERVAL_SECONDS = 15
HEARTBEAT_TTL_SECONDS = 90
logger = logging.getLogger(__name__)


def create_redis_client():
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


class SchedulerHeartbeat:
    def __init__(self):
        self.status = "starting"

    async def run(self):
        if not settings.REDIS_URL:
            logger.warning("REDIS_URL belum dikonfigurasi; heartbeat tidak tersedia.")
            return

        client = create_redis_client()
        try:
            while True:
                try:
                    await client.set(
                        HEARTBEAT_KEY,
                        self.status,
                        ex=HEARTBEAT_TTL_SECONDS,
                    )
                    HEARTBEAT_FILE.touch()
                except Exception:
                    logger.exception("Gagal mengirim heartbeat scheduler.")
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        finally:
            await client.aclose()
