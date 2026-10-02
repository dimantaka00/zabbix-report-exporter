# backend/app/api/router.py

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    hosts,
    dashboards,
    graphs,
    reports,
    schedules,
    settings
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/v1/auth", tags=["Auth"])
api_router.include_router(hosts.router, prefix="/v1/hosts", tags=["Hosts"])
api_router.include_router(
    dashboards.router,
    prefix="/v1/dashboards",
    tags=["Dashboards"]
)
api_router.include_router(graphs.router, prefix="/v1/graphs", tags=["Graphs"])
api_router.include_router(reports.router, prefix="/v1/reports", tags=["Reports"])
api_router.include_router(
    schedules.router,
    prefix="/v1/schedules",
    tags=["Schedules"]
)
api_router.include_router(
    settings.router,
    prefix="/v1/settings",
    tags=["Settings"]
)