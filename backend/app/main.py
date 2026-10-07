from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.router import api_router
from app.core.database import close_db, init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield

    await close_db()


app = FastAPI(
    title="Zabbix Report Exporter",
    version="1.0.0",
    lifespan=lifespan,
)


app.include_router(
    health_router,
)

app.include_router(
    api_router,
    prefix="/api/v1",
)
