"""Server-side sessions, password hashing and local access attribution."""
import asyncio
import hashlib
import hmac
import ipaddress
import logging
import secrets
import socket
import time
from pathlib import Path

import maxminddb
from fastapi import Request

from app.core.config import settings
from app.core.database import get_pool

COOKIE = "zabbix_session"
logger = logging.getLogger(__name__)
_proxy_cache = (0, set())
_geo_reader = None
_geo_stamp = None


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash("unused-constant-time-password")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def trusted_proxy(peer):
    global _proxy_cache
    now = time.monotonic()
    if now - _proxy_cache[0] > 30:
        try:
            rows = await asyncio.get_running_loop().getaddrinfo(settings.AUTH_TRUSTED_PROXY_HOST, None)
            _proxy_cache = (now, {row[4][0] for row in rows})
        except socket.gaierror:
            _proxy_cache = (now, set())
    return peer in _proxy_cache[1]


def country_for(ip):
    global _geo_reader, _geo_stamp
    address = ipaddress.ip_address(ip)
    if not address.is_global:
        return {"country_code": None, "country_name": "Jaringan internal / lokal", "ip_kind": "internal"}
    try:
        path = Path(settings.GEOIP_DATABASE)
        stamp = (str(path), path.stat().st_mtime_ns)
        if stamp != _geo_stamp:
            if _geo_reader:
                _geo_reader.close()
            _geo_reader = maxminddb.open_database(str(path))
            _geo_stamp = stamp
        country = (_geo_reader.get(ip) or {}).get("country", {})
        return {"country_code": country.get("iso_code"),
                "country_name": country.get("names", {}).get("en") or "Tidak diketahui",
                "ip_kind": "public"}
    except (OSError, ValueError, maxminddb.InvalidDatabaseError):
        return {"country_code": None, "country_name": "Tidak diketahui", "ip_kind": "public"}


async def client_details(request):
    peer = request.client.host if request.client else "0.0.0.0"
    is_proxy = await trusted_proxy(peer)
    candidate = request.headers.get("x-real-ip", peer) if is_proxy else peer
    try:
        address = ipaddress.ip_address(candidate)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        ip = str(address)
    except ValueError:
        ip = "0.0.0.0"
    return {"ip": ip, **country_for(ip), "user_agent": request.headers.get("user-agent", "")[:512],
            "scheme": request.headers.get("x-forwarded-proto", request.url.scheme) if is_proxy else request.url.scheme}


def valid_origin(request, details):
    origin = request.headers.get("origin")
    return origin is None or origin == f"{details['scheme']}://{request.headers.get('host', '')}"


async def record_event(request, event_type, status, username=None, user_id=None, path=None):
    details = request.state.access_details
    await get_pool().execute("""
        INSERT INTO access_events(user_id,username,event_type,ip,country_code,country_name,ip_kind,
                                  user_agent,method,path,status_code)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    """, user_id, username, event_type, details["ip"], details["country_code"], details["country_name"],
        details["ip_kind"], details["user_agent"], request.method[:16], (path or request.url.path)[:256], status)


async def initialize_access():
    # Serialize first-admin bootstrap across backend and worker processes.
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(714001)")
        exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM app_users)")
        if not exists:
            password = settings.AUTH_BOOTSTRAP_PASSWORD
            if len(password) < 12 or len(password) > 128 or password.startswith(("REPLACE_WITH", "CHANGE_ME")):
                raise RuntimeError("Set AUTH_BOOTSTRAP_PASSWORD dengan 12–128 karakter sebelum startup pertama.")
            encoded = await asyncio.to_thread(password_hash, password)
            await conn.execute("""INSERT INTO app_users(username,display_name,password_hash,role)
                VALUES($1,'Administrator',$2,'admin')""", settings.AUTH_BOOTSTRAP_USERNAME, encoded)


async def cleanup_access():
    while True:
        try:
            await get_pool().execute("DELETE FROM app_sessions WHERE expires_at<NOW()")
            await get_pool().execute("DELETE FROM access_events WHERE occurred_at<NOW()-($1::int * INTERVAL '1 day')",
                                     settings.AUDIT_RETENTION_DAYS)
        except Exception:
            logger.exception("Access log retention maintenance failed")
        await asyncio.sleep(3600)


class AccessMiddleware:
    """Protect every API route, including direct file downloads, before dispatch."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/"):
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        if not settings.AUTH_ENABLED:
            from starlette.responses import Response
            path = scope["path"]
            if path == "/api/v1/auth/check":
                return await Response(status_code=204, headers={"Cache-Control": "no-store"})(scope, receive, send)
            if path == "/api/v1/auth/me":
                return await JSONResponse({"success": True, "data": {"authentication_enabled": False}},
                                          headers={"Cache-Control": "no-store"})(scope, receive, send)
            # Disabling login must never make account management or private audit logs public.
            if path.startswith(("/api/v1/auth/", "/api/v1/admin/")):
                return await JSONResponse({"detail": "Fitur login dan dashboard admin sedang nonaktif."},
                                          status_code=403)(scope, receive, send)
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        request.state.access_details = await client_details(request)
        path = scope["path"]
        session = None
        if path != "/api/v1/auth/login":
            token = request.cookies.get(COOKIE, "")
            if 20 <= len(token) <= 128:
                session = await get_pool().fetchrow("""
                    SELECT s.id AS session_id,s.csrf_token,u.id,u.username,u.display_name,u.role,u.must_change_password
                    FROM app_sessions s JOIN app_users u ON u.id=s.user_id
                    WHERE s.token_hash=$1 AND s.expires_at>NOW() AND u.active
                """, token_hash(token))
            if session is None:
                await record_event(request, "access_denied", 401)
                return await JSONResponse({"detail": "Silakan login."}, status_code=401)(scope, receive, send)
            request.state.user = dict(session)
            if path.startswith("/api/v1/admin/") and session["role"] != "admin":
                await record_event(request, "access_denied", 403, session["username"], session["id"])
                return await JSONResponse({"detail": "Akses khusus admin."}, status_code=403)(scope, receive, send)
            allowed = {"/api/v1/auth/me", "/api/v1/auth/check", "/api/v1/auth/password", "/api/v1/auth/logout", "/api/v1/auth/visit"}
            if session["must_change_password"] and path not in allowed:
                return await JSONResponse({"detail": "PASSWORD_CHANGE_REQUIRED"}, status_code=403)(scope, receive, send)
            if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
                supplied = request.headers.get("x-csrf-token", "")
                if not valid_origin(request, request.state.access_details) or not hmac.compare_digest(supplied.encode(), session["csrf_token"].encode()):
                    await record_event(request, "csrf_denied", 403, session["username"], session["id"])
                    return await JSONResponse({"detail": "Permintaan tidak valid. Muat ulang halaman."}, status_code=403)(scope, receive, send)
            d = request.state.access_details
            await get_pool().execute("""UPDATE app_sessions SET last_seen=NOW(),ip=$2,country_code=$3,
                country_name=$4,ip_kind=$5,user_agent=$6 WHERE id=$1""", session["session_id"], d["ip"],
                d["country_code"], d["country_name"], d["ip_kind"], d["user_agent"])
        elif not valid_origin(request, request.state.access_details):
            await record_event(request, "csrf_denied", 403)
            return await JSONResponse({"detail": "Origin tidak diizinkan."}, status_code=403)(scope, receive, send)

        status = 500
        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [(b"cache-control", b"no-store")]
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            if session and path not in ("/api/v1/auth/check", "/api/v1/auth/visit"):
                await record_event(request, "request", status, session["username"], session["id"])
