"""Host availability from explicit Zabbix problem/recovery events."""

import re


STATUS_LABELS = {"online": "Up", "offline": "Down", "unknown": "Unknown",
                 "recovered": "Down", "ongoing": "Down", "unconfigured": "Not configured"}


def recommended_trigger(trigger):
    if any(tag.get("tag") == "report" and tag.get("value") == "host-downtime"
           for tag in trigger.get("tags", [])):
        return True
    keys = [item.get("key_", "").split("[")[0] for item in trigger.get("items", [])]
    return bool(keys and all(key == "icmpping" for key in keys)
                and re.search(r"(?:=\s*0\b|<\s*1\b)", trigger.get("expression", "")))


def duration_text(seconds):
    if seconds is None:
        return "-"
    days, remainder = divmod(max(int(seconds), 0), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    clock = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{days} d {clock}" if days else clock


def duration_detail(seconds):
    if seconds is None:
        return "-"
    days, remainder = divmod(max(int(seconds), 0), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = [(days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s")]
    return " ".join(f"{value} {unit}" for value, unit in parts if value) or "0 s"


def union_seconds(intervals):
    total, end = 0, None
    for left, right in sorted(intervals):
        if right <= left:
            continue
        total += max(0, right - max(left, end if end is not None else left))
        end = max(end if end is not None else right, right)
    return total


def downtime_result(host, trigger, events, recoveries, last_event, start, end, now):
    rows, intervals, incomplete = [], [], False
    boundary = min(end + 1, now)
    recovery_by_id = {event["eventid"]: event for event in recoveries}
    for event in sorted({event["eventid"]: event for event in events}.values(),
                        key=lambda event: (int(event["clock"]), int(event["eventid"]))):
        began = int(event["clock"])
        recovery_id = event.get("r_eventid", "0")
        recovery = recovery_by_id.get(recovery_id)
        finished = int(recovery["clock"]) if recovery and recovery.get("value") == "0" else None
        missing = recovery_id != "0" and finished is None
        if finished is not None and finished < began:
            missing, finished = True, None
        if began > min(end, now) or (finished is not None and finished <= start):
            continue
        incomplete |= missing
        status = "unknown" if missing else ("recovered" if finished is not None else "ongoing")
        duration = None if missing else max((finished if finished is not None else now) - began, 0)
        clipped = None if missing else max(min(finished if finished is not None else now, boundary) - max(began, start), 0)
        rows.append({"event_id": event["eventid"], "status": status, "start_time": began,
                     "end_time": finished, "duration_seconds": duration,
                     "period_duration_seconds": clipped})
        if clipped is not None:
            intervals.append((max(began, start), min(finished if finished is not None else now, boundary)))
    current = "unknown"
    if host.get("status") == "0" and trigger.get("status") == "0" and trigger.get("state") == "0":
        current = {"0": "online", "1": "offline"}.get(trigger.get("value"), "unknown")
    at_end = {"0": "online", "1": "offline"}.get((last_event or {}).get("value"), "unknown")
    warning = "Recovery events are unavailable; durations that cannot be verified are shown as unknown." if incomplete else None
    return {"host": host, "trigger": trigger, "source": "Zabbix trigger events", "status": "available",
            "current_status": current, "status_at_end": at_end, "time_from": start, "time_till": end,
            "as_of": now, "events": rows, "total_downtime_seconds": None if incomplete else union_seconds(intervals),
            "warning": warning}


async def collect_host_downtime(client, host_id, host_name, start, end, trigger_id=None):
    try:
        if not host_id:
            host_id = (await client.get_host_by_name(host_name))["hostid"]
        return await client.get_host_downtime(host_id, start, end, trigger_id)
    except Exception as exc:
        warning = str(exc) if isinstance(exc, ValueError) else "Downtime data is unavailable. Check the Zabbix connection and event read permissions."
        return {"status": "unavailable", "current_status": "unknown", "status_at_end": "unknown",
                "host": {"hostid": host_id, "name": host_name}, "trigger": None, "events": [],
                "time_from": start, "time_till": end, "total_downtime_seconds": None, "warning": warning}
