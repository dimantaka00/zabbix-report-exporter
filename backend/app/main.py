from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.zabbix import router as zabbix_router
from app.api.v1.reports import router as reports_router
from app.api.v1.schedules import router as schedules_router
from app.core.database import close_db, init_db
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.history import router as history_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield

    await close_db()


app = FastAPI(
    title="Zabbix Report Exporter",
    version="0.2.0",
    lifespan=lifespan,
)


app.include_router(
    health_router,
)

app.include_router(
    zabbix_router,
    prefix="/api/v1",
)

app.include_router(
    reports_router,
    prefix="/api/v1",
)

app.include_router(
    schedules_router,
    prefix="/api/v1",
)

app.include_router(
    dashboard_router,
    prefix="/api/v1"
)

app.include_router(
    history_router,
    prefix="/api/v1"
)