"""Hold a PostgreSQL lock while the full snapshot copies its database and report files.

Runs temporarily inside the backend container; credentials never leave its environment.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg


async def main():
    token = Path(sys.argv[1])
    if token.parent != Path('/tmp') or not token.name.startswith('backup-report-guard-'):
        raise ValueError('Invalid backup guard token')
    pid, ready, stop, failed = [Path(str(token)+suffix) for suffix in ('.pid','.ready','.stop','.failed')]
    pid.write_text(str(os.getpid()))
    conn = None
    try:
        async with asyncio.timeout(7200):
            url = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1)
            conn = await asyncpg.connect(url)
            await conn.execute('SELECT pg_advisory_lock(710705,0)')
            ready.write_text('ready')
            while not stop.exists():
                await asyncio.sleep(.25)
    except Exception as exc:
        failed.write_text(type(exc).__name__)
        raise SystemExit(1)
    finally:
        if conn:
            await conn.close()  # Closing the session also releases the advisory lock.
        ready.unlink(missing_ok=True)


if __name__ == '__main__':
    asyncio.run(main())
