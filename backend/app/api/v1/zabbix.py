from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings
from app.services.zabbix.client import ZabbixClient

router = APIRouter(prefix="/zabbix", tags=["Zabbix"])


async def request(method, *args, **kwargs):
    try:
        return await getattr(ZabbixClient(), method)(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(502, "Permintaan Zabbix gagal. Periksa koneksi dan hak akses API token.")


def period(start, end):
    if end <= start or end-start > settings.MAX_REPORT_DAYS*86400:
        raise HTTPException(400, f"Periode harus positif dan maksimal {settings.MAX_REPORT_DAYS} hari.")


@router.get("/version")
async def version():
    return {"success": True, "zabbix_version": await request("api_version")}


@router.get("/hosts")
async def hosts():
    return {"success": True, "data": await request("get_hosts")}


@router.get("/hosts/by-name/{host_name}/items")
async def items_by_host_name(host_name: str):
    return {"success": True, "host_name": host_name, "data": await request("get_items_by_host_name", host_name)}


@router.get("/hosts/{hostid}/items")
async def items(hostid: str):
    return {"success": True, "hostid": hostid, "data": await request("get_items", hostid)}


@router.get("/hosts/{hostid}/graphs")
async def graphs(hostid: str):
    return {"success": True, "hostid": hostid, "data": await request("get_graphs", hostid)}


@router.get("/items/{itemid}/history")
async def history(itemid: str, history_type: int = Query(..., ge=0, le=5),
                  time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0)):
    period(time_from, time_till)
    data = await request("_complete_history", itemid, history_type, time_from, time_till)
    return {"success": True, "itemid": itemid, "data": data}


@router.get("/items/{itemid}/trends")
async def trends(itemid: str, time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0)):
    period(time_from, time_till)
    return {"success": True, "itemid": itemid, "data": await request("get_trends", itemid, time_from, time_till)}


@router.get("/items/{itemid}/data")
async def item_data(itemid: str, time_from: int = Query(..., ge=0), time_till: int = Query(..., ge=0)):
    period(time_from, time_till)
    return {"success": True, "data": await request("get_item_data", itemid, time_from, time_till)}
