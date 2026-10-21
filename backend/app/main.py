from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.router import api_router
from app.core.database import close_db, init_db
from app.core.config import settings
from app.services.access import AccessMiddleware, initialize_access, cleanup_access
from app.api.v1.access import router as access_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.AUTH_ENABLED:
        await initialize_access()
    maintenance = asyncio.create_task(cleanup_access())
    try:
        yield
    finally:
        maintenance.cancel()
        await asyncio.gather(maintenance, return_exceptions=True)
        await close_db()


app = FastAPI(
    title="Zabbix Report Exporter",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)
app.add_middleware(AccessMiddleware)
app.include_router(access_router, prefix="/api/v1")


app.include_router(
    health_router,
)

app.include_router(
    api_router,
    prefix="/api/v1",
)
