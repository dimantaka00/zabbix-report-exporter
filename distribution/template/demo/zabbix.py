"""Synthetic read-only Zabbix JSON-RPC demo; never used by production Compose."""
import json
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GROUPS = [{"groupid": "1", "name": "DEMO / Routers"}, {"groupid": "2", "name": "DEMO / Servers"}]
HOSTS = [{"hostid": str(index), "host": f"demo-edge-{index:02}", "name": f"DEMO Edge {index:02}", "status": "0",
          "description": "Synthetic host for client implementation examples.", "monitored_by": "0", "proxyid": "0",
          "hostgroups": [GROUPS[0]], "groups": [GROUPS[0]], "parentTemplates": [],
          "interfaces": [{"interfaceid": str(index), "type": "2", "main": "1", "ip": f"192.0.2.{index+10}",
                          "dns": "", "useip": "1", "port": "161", "available": "1", "details": {"version": "2", "bulk": "1"}}]}
         for index in range(1, 4)]
ITEMS = [{"itemid": str(index*100+offset), "hostid": str(index), "name": name, "key_": key,
          "units": units, "value_type": "0", "status": "0", "state": "0", "history": "90d", "trends": "365d"}
         for index in range(1, 4) for offset, name, key, units in (
             (1, "WAN: Bits received", "net.if.in[wan]", "bps"), (2, "WAN: Bits sent", "net.if.out[wan]", "bps"),
             (3, "CPU utilization", "system.cpu.util", "%"))]


def selection(rows, params, parameter, field):
    ids = params.get(parameter)
    if ids is None:
        return rows
    if not isinstance(ids, list):
        ids = [ids]
    return [row for row in rows if row[field] in [str(value) for value in ids]]


def value(item_id, timestamp):
    wave = math.sin(timestamp/1800 + int(item_id))
    if str(item_id).endswith("3"):
        return round(32+18*wave, 3)
    base = 16_000_000 if str(item_id).endswith("1") else 6_000_000
    return round(base*(1+0.45*wave+0.15*math.sin(timestamp/137)), 2)


def rpc(method, params):
    if method == "apiinfo.version":
        return "7.0.0"
    if method == "host.get":
        rows = selection(HOSTS, params, "hostids", "hostid")
        if params.get("groupids") and "1" not in [str(v) for v in params["groupids"]]:
            rows = []
        if params.get("filter", {}).get("name"):
            rows = [row for row in rows if row["name"] in params["filter"]["name"]]
        return rows[:params.get("limit", len(rows))]
    if method == "hostgroup.get":
        return GROUPS
    if method == "item.get":
        rows = selection(ITEMS, params, "hostids", "hostid")
        return selection(rows, params, "itemids", "itemid")
    if method in ("history.get", "trend.get"):
        ids = params.get("itemids", ["101"])
        item_id = str(ids[0] if isinstance(ids, list) else ids)
        start, end = int(params.get("time_from", time.time()-86400)), min(int(params.get("time_till", time.time())), int(time.time()))
        step = 3600 if method == "trend.get" else 60
        times = range((start+step-1)//step*step, end+1, step)
        rows = []
        for timestamp in times:
            sample = value(item_id, timestamp)
            row = {"itemid": item_id, "clock": str(timestamp)}
            row.update({"value_min": str(sample*.9), "value_max": str(sample*1.1), "value_avg": str(sample), "num": "60"}
                       if method == "trend.get" else {"ns": "0", "value": str(sample)})
            rows.append(row)
            if len(rows) >= int(params.get("limit", 5000)):
                break
        return rows
    if method == "trigger.get":
        host_ids = params.get("hostids", ["1"])
        host_id = str(host_ids[0] if isinstance(host_ids, list) else host_ids)
        return [{"triggerid": str(int(host_id)+900), "description": "Unavailable by ICMP ping", "expression": "last(/demo/icmpping)=0",
                 "value": "0", "status": "0", "state": "0", "hosts": [{"hostid": host_id}],
                 "items": [{"key_": "icmpping"}], "tags": [{"tag": "report", "value": "host-downtime"}]}]
    if method == "event.get":
        if isinstance(params.get("value"), list):
            return [{"eventid": "1", "clock": str(int(params.get("time_till", time.time()))-3600), "value": "0"}]
        return []
    if method in ("graph.get", "proxy.get", "proxygroup.get"):
        return []
    raise ValueError("Unsupported demo method")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, result):
        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 404, {"status": "ok", "demo": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            return self.respond(413, {"error": "request too large"})
        try:
            request = json.loads(self.rfile.read(length))
            if request["method"] != "apiinfo.version" and self.headers.get("Authorization") != "Bearer demo-read-only-token":
                return self.respond(200, {"jsonrpc": "2.0", "id": request.get("id"), "error": {"message": "Not authorized"}})
            result = rpc(request["method"], request.get("params", {}))
            self.respond(200, {"jsonrpc": "2.0", "id": request.get("id"), "result": result})
        except (ValueError, KeyError, TypeError):
            self.respond(400, {"error": "invalid demo request"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
