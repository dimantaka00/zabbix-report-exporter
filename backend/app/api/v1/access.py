import asyncio
import secrets
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

from app.core.config import settings
from app.core.database import get_pool
from app.services.access import COOKIE, DUMMY_HASH, password_hash, verify_password, token_hash, record_event

router = APIRouter(tags=["Access"])
Username = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class NewUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    display_name: str = Field(min_length=1, max_length=100)
    password: Password
    role: Literal["admin", "operator"] = "operator"


class UserStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


class ResetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: Password


class ChangePassword(ResetPassword):
    current_password: str = Field(min_length=1, max_length=128)


class Visit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Literal["/", "/reports", "/schedules", "/admin", "/password"]


def public_user(user):
    return {key: user[key] for key in ("id", "username", "display_name", "role", "must_change_password")}


async def issue_session(request, response, user):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    d = request.state.access_details
    await get_pool().execute("""INSERT INTO app_sessions(token_hash,user_id,csrf_token,ip,country_code,
        country_name,ip_kind,user_agent,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,
        NOW()+($9::int * INTERVAL '1 hour'))""", token_hash(token), user["id"], csrf, d["ip"],
        d["country_code"], d["country_name"], d["ip_kind"], d["user_agent"], settings.AUTH_SESSION_HOURS)
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.AUTH_COOKIE_SECURE,
                        samesite="lax", max_age=settings.AUTH_SESSION_HOURS*3600, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"success": True, "data": {**public_user(user), "csrf_token": csrf}}


@router.post("/auth/login")
async def login(payload: Login, request: Request, response: Response):
    username = payload.username.strip().lower()
    ip = request.state.access_details["ip"]
    # Lock per IP so concurrent guesses cannot race the attempt counter.
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,714002))", ip)
        blocked = await conn.fetchval("""SELECT COUNT(*)>=25 OR COUNT(*) FILTER(WHERE username=$2)>=8
            FROM access_events WHERE ip=$1 AND event_type='login_failed'
            AND occurred_at>NOW()-INTERVAL '10 minutes'""", ip, username)
        if blocked:
            raise HTTPException(429, "Terlalu banyak percobaan login. Coba lagi dalam 10 menit.")
        user = await conn.fetchrow("SELECT * FROM app_users WHERE username=$1", username)
        valid = await asyncio.to_thread(verify_password, payload.password, user["password_hash"] if user else DUMMY_HASH)
        if not valid or not user or not user["active"]:
            d = request.state.access_details
            await conn.execute("""INSERT INTO access_events(username,event_type,ip,country_code,country_name,
                ip_kind,user_agent,method,path,status_code) VALUES($1,'login_failed',$2,$3,$4,$5,$6,'POST','/api/v1/auth/login',401)""",
                username, d["ip"], d["country_code"], d["country_name"], d["ip_kind"], d["user_agent"])
            user = None
    if user is None:
        raise HTTPException(401, "Username atau password salah.")
    result = await issue_session(request, response, user)
    await record_event(request, "login_success", 200, user["username"], user["id"])
    return result


@router.get("/auth/me")
async def me(request: Request):
    return {"success": True, "data": {**public_user(request.state.user), "csrf_token": request.state.user["csrf_token"]}}


@router.get("/auth/check", status_code=204)
async def check():
    return Response(status_code=204)


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    user = request.state.user
    await get_pool().execute("DELETE FROM app_sessions WHERE id=$1", user["session_id"])
    response.delete_cookie(COOKIE, path="/", secure=settings.AUTH_COOKIE_SECURE, httponly=True, samesite="lax")
    await record_event(request, "logout", 200, user["username"], user["id"])
    return {"success": True}


@router.post("/auth/password")
async def change_password(payload: ChangePassword, request: Request, response: Response):
    user = request.state.user
    encoded = await get_pool().fetchval("SELECT password_hash FROM app_users WHERE id=$1", user["id"])
    if not await asyncio.to_thread(verify_password, payload.current_password, encoded):
        raise HTTPException(400, "Password saat ini salah.")
    if payload.password == payload.current_password:
        raise HTTPException(400, "Gunakan password baru yang berbeda.")
    hashed = await asyncio.to_thread(password_hash, payload.password)
    async with get_pool().acquire() as conn, conn.transaction():
        updated = await conn.fetchrow("""UPDATE app_users SET password_hash=$1,must_change_password=FALSE
            WHERE id=$2 AND password_hash=$3 AND active RETURNING *""", hashed, user["id"], encoded)
        if not updated:
            raise HTTPException(409, "Akun berubah. Silakan login kembali.")
        await conn.execute("DELETE FROM app_sessions WHERE user_id=$1", user["id"])
    await record_event(request, "password_changed", 200, user["username"], user["id"])
    return await issue_session(request, response, updated)


@router.post("/auth/visit")
async def visit(payload: Visit, request: Request):
    user = request.state.user
    await record_event(request, "page_view", 200, user["username"], user["id"], payload.path)
    return {"success": True}


@router.get("/admin/summary")
async def summary():
    pool = get_pool()
    totals = await pool.fetchrow("""SELECT COUNT(*) AS total_events,COUNT(DISTINCT ip) AS unique_ips,
        COUNT(DISTINCT user_id) AS unique_users,COUNT(*) FILTER(WHERE event_type='login_success') AS successful_logins,
        COUNT(*) FILTER(WHERE event_type='login_failed') AS failed_logins
        FROM access_events WHERE occurred_at>=DATE_TRUNC('day',NOW() AT TIME ZONE 'Asia/Jakarta') AT TIME ZONE 'Asia/Jakarta'""")
    online = await pool.fetchval("""SELECT COUNT(*) FROM app_sessions s JOIN app_users u ON u.id=s.user_id
        WHERE s.expires_at>NOW() AND s.last_seen>NOW()-INTERVAL '5 minutes' AND u.active""")
    countries = await pool.fetch("""SELECT country_name,country_code,COUNT(*) AS total FROM access_events
        WHERE occurred_at>NOW()-INTERVAL '24 hours' GROUP BY country_name,country_code ORDER BY total DESC LIMIT 10""")
    return {"success": True, "data": {**dict(totals), "online_sessions": online,
        "countries": [dict(row) for row in countries], "geoip_available": Path(settings.GEOIP_DATABASE).is_file()}}


@router.get("/admin/events")
async def events(q: str = Query("", max_length=100), event_type: str = Query("", max_length=32),
                 days: int = Query(7, ge=1, le=90), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    pool = get_pool()
    where = """occurred_at>NOW()-($1::int * INTERVAL '1 day')
        AND ($2='' OR username ILIKE '%'||$2||'%' OR ip ILIKE '%'||$2||'%' OR country_name ILIKE '%'||$2||'%')
        AND ($3='' OR event_type=$3)"""
    rows = await pool.fetch(f"SELECT * FROM access_events WHERE {where} ORDER BY occurred_at DESC,id DESC LIMIT $4 OFFSET $5",
                            days, q, event_type, limit, offset)
    count = await pool.fetchval(f"SELECT COUNT(*) FROM access_events WHERE {where}", days, q, event_type)
    return {"success": True, "data": [dict(row) for row in rows], "total": count}


@router.get("/admin/sessions")
async def sessions():
    rows = await get_pool().fetch("""SELECT s.id,u.username,u.display_name,s.ip,s.country_name,s.country_code,
        s.ip_kind,s.user_agent,s.created_at,s.last_seen,s.expires_at,
        (s.last_seen>NOW()-INTERVAL '5 minutes') AS online
        FROM app_sessions s JOIN app_users u ON u.id=s.user_id WHERE s.expires_at>NOW() AND u.active
        ORDER BY s.last_seen DESC LIMIT 200""")
    return {"success": True, "data": [dict(row) for row in rows]}


@router.delete("/admin/sessions/{session_id}")
async def revoke(session_id: int, request: Request):
    await get_pool().execute("DELETE FROM app_sessions WHERE id=$1", session_id)
    await record_event(request, "session_revoked", 200, request.state.user["username"], request.state.user["id"])
    return {"success": True}


@router.get("/admin/users")
async def users():
    rows = await get_pool().fetch("SELECT id,username,display_name,role,active,must_change_password,created_at FROM app_users ORDER BY id LIMIT 1000")
    return {"success": True, "data": [dict(row) for row in rows]}


@router.post("/admin/users")
async def create_user(payload: NewUser, request: Request):
    hashed = await asyncio.to_thread(password_hash, payload.password)
    row = await get_pool().fetchrow("""INSERT INTO app_users(username,display_name,password_hash,role)
        VALUES($1,$2,$3,$4) ON CONFLICT(username) DO NOTHING RETURNING id""",
        payload.username, payload.display_name.strip(), hashed, payload.role)
    if not row:
        raise HTTPException(409, "Username sudah digunakan.")
    await record_event(request, "account_created", 200, request.state.user["username"], request.state.user["id"])
    return {"success": True, "data": {"id": row["id"]}}


@router.patch("/admin/users/{user_id}/status")
async def user_status(user_id: int, payload: UserStatus, request: Request):
    if user_id == request.state.user["id"] and not payload.active:
        raise HTTPException(400, "Anda tidak dapat menonaktifkan akun sendiri.")
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(714003)")
        user = await conn.fetchrow("SELECT * FROM app_users WHERE id=$1", user_id)
        if not user:
            raise HTTPException(404, "Akun tidak ditemukan.")
        count = await conn.fetchval("SELECT COUNT(*) FROM app_users WHERE role='admin' AND active")
        if user["role"] == "admin" and user["active"] and not payload.active and count <= 1:
            raise HTTPException(400, "Admin terakhir harus tetap aktif.")
        await conn.execute("UPDATE app_users SET active=$1 WHERE id=$2", payload.active, user_id)
        if not payload.active:
            await conn.execute("DELETE FROM app_sessions WHERE user_id=$1", user_id)
    await record_event(request, "account_status_changed", 200, request.state.user["username"], request.state.user["id"])
    return {"success": True}


@router.post("/admin/users/{user_id}/password")
async def reset_password(user_id: int, payload: ResetPassword, request: Request):
    hashed = await asyncio.to_thread(password_hash, payload.password)
    async with get_pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("UPDATE app_users SET password_hash=$1,must_change_password=TRUE WHERE id=$2 RETURNING id", hashed, user_id)
        if not row:
            raise HTTPException(404, "Akun tidak ditemukan.")
        await conn.execute("DELETE FROM app_sessions WHERE user_id=$1", user_id)
    await record_event(request, "password_reset", 200, request.state.user["username"], request.state.user["id"])
    return {"success": True}
