"""Example: list hosts, preview one metric, and download a PDF through the API.

Default target is the isolated synthetic demo. Production requires an account whose
bootstrap password has already been changed in the web UI.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:5011")
    parser.add_argument("--host-id", default="1")
    parser.add_argument("--item-ids", default="101,102")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise SystemExit("Output already exists; choose another filename.")
    base = args.base_url.rstrip("/") + "/api/v1"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = ""

    def call(path, payload=None, binary=False):
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(base+path, data=body, headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
        with opener.open(request, timeout=240) as response:
            result = response.read()
            return result if binary else json.loads(result)

    try:
        account = call("/auth/me")["data"]
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        username = os.environ.get("REPORT_USERNAME") or input("Username: ").strip()
        password = getpass.getpass("Password: ")
        account = call("/auth/login", {"username": username, "password": password})["data"]
    csrf = account.get("csrf_token", "")
    if account.get("must_change_password"):
        raise SystemExit("Change the bootstrap password in the web UI before using this example.")
    hosts = call("/zabbix/hosts?server_id=primary")["data"]
    host = next((host for host in hosts if host["hostid"] == args.host_id), None)
    if host is None:
        print(json.dumps(hosts, indent=2))
        raise SystemExit("Select a host_id from the list above.")
    items = args.item_ids.split(",")
    end = int(time.time())
    period = {"time_from": end-3600, "time_till": end}
    query = urllib.parse.urlencode({**period, "server_id": "primary", "resolution": "minute"})
    preview = call(f"/zabbix/items/{items[0]}/data?{query}")["data"]
    print(json.dumps({"host": host["name"], "metric": preview["item"]["name"], "samples": len(preview["points"]), "summary": preview["summary"]}, indent=2))
    if args.output:
        pdf = call("/reports/generate", {"zabbix_server": "primary", "host_id": host["hostid"],
            "host_name": host["name"], "item_ids": items, **period, "resolution": "minute",
            "title": "API implementation example", "timezone": "UTC", "include_downtime": False,
            "chart_mode": "combined" if len(items)>1 else "separate"}, binary=True)
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf:
            raise SystemExit("Incomplete PDF response.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as file:
            file.write(pdf)
        print(f"PDF saved: {args.output} ({len(pdf)} bytes)")


if __name__ == "__main__":
    main()
