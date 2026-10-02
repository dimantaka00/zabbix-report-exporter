from fastapi import APIRouter, HTTPException, Query

from app.services.zabbix.client import ZabbixClient


router = APIRouter(
    prefix="/zabbix",
    tags=["Zabbix"],
)


@router.get("/version")
async def version():
    try:
        client = ZabbixClient()

        result = await client.api_version()

        return {
            "success": True,
            "zabbix_version": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/hosts")
async def hosts():
    try:
        client = ZabbixClient()

        result = await client.get_hosts()

        return {
            "success": True,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/hosts/by-name/{host_name}/items")
async def items_by_host_name(host_name: str):
    try:
        client = ZabbixClient()

        result = await client.get_items_by_host_name(
            host_name
        )

        return {
            "success": True,
            "host_name": host_name,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/hosts/{hostid}/items")
async def items(hostid: str):
    try:
        client = ZabbixClient()

        result = await client.get_items(
            hostid
        )

        return {
            "success": True,
            "hostid": hostid,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/hosts/{hostid}/graphs")
async def graphs(hostid: str):
    try:
        client = ZabbixClient()

        result = await client.get_graphs(
            hostid
        )

        return {
            "success": True,
            "hostid": hostid,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/items/{itemid}/history")
async def history(
    itemid: str,
    history_type: int = Query(...),
    time_from: int = Query(...),
    time_till: int = Query(...),
):
    try:
        client = ZabbixClient()

        result = await client.get_history(
            itemid=itemid,
            history_type=history_type,
            time_from=time_from,
            time_till=time_till,
        )

        return {
            "success": True,
            "itemid": itemid,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/items/{itemid}/trends")
async def trends(
    itemid: str,
    time_from: int = Query(...),
    time_till: int = Query(...),
):
    try:
        client = ZabbixClient()

        result = await client.get_trends(
            itemid=itemid,
            time_from=time_from,
            time_till=time_till,
        )

        return {
            "success": True,
            "itemid": itemid,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/items/{itemid}/data")
async def item_data(
    itemid: str,
    time_from: int = Query(...),
    time_till: int = Query(...),
):
    try:
        if time_till <= time_from:
            raise HTTPException(
                status_code=400,
                detail=(
                    "time_till harus lebih besar "
                    "dari time_from."
                ),
            )

        client = ZabbixClient()

        result = await client.get_item_data(
            itemid=itemid,
            time_from=time_from,
            time_till=time_till,
        )

        return {
            "success": True,
            "data": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )