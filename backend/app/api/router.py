from fastapi import APIRouter

from app.api.v1 import dashboard, history, reports, schedules, zabbix


api_router = APIRouter()

for router in (
    zabbix.router,
    reports.router,
    schedules.router,
    dashboard.router,
    history.router,
):
    api_router.include_router(router)
