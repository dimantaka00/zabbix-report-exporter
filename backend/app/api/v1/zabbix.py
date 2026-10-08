from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.services.zabbix.client import ZabbixClient

router = APIRouter(prefix="/zabbix", tags=["Zabbix"])


async def request(server_id, method, *args, **kwargs):
    try:
        return await getattr(ZabbixClient(server_id), method)(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        if method in ("get_downtime_triggers", "get_host_downtime"):
            raise HTTPException(502, "Downtime data is unavailable. Check the Zabbix connection and event read permissions.")
        raise HTTPException(502, str(exc))
    except Exception:
        if method in ("get_downtime_triggers", "get_host_downtime"):
            raise HTTPException(502, "Downtime data is unavailable. Check the Zabbix connection and event read permissions.")
        raise HTTPException(502, "Permintaan Zabbix gagal. Periksa koneksi dan hak akses API token.")


def period(start, end):
    if end <= start or end-start > settings.MAX_REPORT_DAYS*86400:
        raise HTTPException(400, f"Periode harus positif dan maksimal {settings.MAX_REPORT_DAYS} hari.")


@router.get("/version")
async def version(server_id: str = Query("primary")):
    return {"success": True, "zabbix_version": await request(server_id, "api_version")}


@router.get("/servers")
async def servers():
    return {"success": True, "data": ZabbixClient.configured_servers()}


@router.get("/hosts")
async def hosts(server_id: str = Query("primary")):
    return {"success": True, "data": await request(server_id, "get_hosts")}


@router.get("/hosts/by-name/{host_name}/items")
async def items_by_host_name(host_name: str, server_id: str = Query("primary")):
    return {"success": True, "host_name": host_name,
            "data": await request(server_id, "get_items_by_host_name", host_name)}


@router.get("/hosts/{hostid}/items")
async def items(hostid: str, server_id: str = Query("primary")):
    return {"success": True, "hostid": hostid, "data": await request(server_id, "get_items", hostid)}


@router.get("/hosts/{hostid}/graphs")
async def graphs(hostid: str, server_id: str = Query("primary")):
    return {"success": True, "hostid": hostid,
            "data": await request(server_id, "get_graphs", hostid)}


@router.get("/hosts/{hostid}/downtime-triggers")
async def downtime_triggers(hostid: str, server_id: str = Query("primary")):
    return {"success": True, "data": await request(server_id, "get_downtime_triggers", hostid)}


@router.get("/hosts/{hostid}/downtime")
async def host_downtime(hostid: str, time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0),
                       server_id: str = Query("primary"), trigger_id: str | None = Query(None, pattern=r"^[0-9]+$")):
    if time_till <= time_from or time_till-time_from > settings.MAX_REPORT_DAYS*86400:
        raise HTTPException(400, f"Select a valid period of up to {settings.MAX_REPORT_DAYS} days.")
    return {"success": True, "data": await request(server_id, "get_host_downtime", hostid, time_from, time_till, trigger_id)}


@router.get("/items/{itemid}/history")
async def history(itemid: str, history_type: int = Query(..., ge=0, le=5),
                  time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0),
                  server_id: str = Query("primary")):
    period(time_from, time_till)
    data = await request(server_id, "_complete_history", itemid, history_type, time_from, time_till)
    return {"success": True, "itemid": itemid, "data": data}


@router.get("/items/{itemid}/trends")
async def trends(itemid: str, time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0),
                 server_id: str = Query("primary")):
    period(time_from, time_till)
    return {"success": True, "itemid": itemid,
            "data": await request(server_id, "get_trends", itemid, time_from, time_till)}


@router.get("/items/{itemid}/data")
async def item_data(itemid: str, time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0),
                    server_id: str = Query("primary"),
                    resolution: Literal["auto", "hourly", "minute"] = Query("minute")):
    period(time_from, time_till)
    return {"success": True,
            "data": await request(server_id, "get_item_data", itemid, time_from, time_till, resolution)}
