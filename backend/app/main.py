from datetime import timezone

from quart import Quart, g, jsonify, request

from app.db import SessionLocal
from app.models import Basin
from app.repositories import BasinRepo, OperatorFilterRepo, ReadingRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    ForbiddenError,
    RuleError,
    assert_can_edit_filter,
    assert_can_set_status,
    latest_temp,
    normalize_operators,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _basin_json(basin: Basin) -> dict:
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_set_status(basin, status)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _filter_json(row) -> dict:
    if row is None:
        return {"saved": False, "operators": [], "updatedBy": None, "updatedAt": None}
    return {
        "saved": True,
        "operators": list(row.operators or []),
        "updatedBy": row.updated_by,
        "updatedAt": _iso(row.updated_at),
    }


def _reading_json(reading) -> dict:
    return {
        "id": reading.id,
        "basinId": reading.basin_id,
        "basinCode": reading.basin.code if reading.basin else "",
        "waterTempC": reading.water_temp_c,
        "operator": reading.operator,
        "takenAt": _iso(reading.taken_at),
    }


@app.route("/api/operators")
async def operators():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        return {"operators": await ReadingRepo(session).operators()}


@app.route("/api/operator-filter")
async def get_operator_filter():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        row = await OperatorFilterRepo(session).get()
        return _filter_json(row)


@app.route("/api/operator-filter", methods=["PUT", "POST"])
async def save_operator_filter():
    denied = require_user()
    if denied:
        return denied
    try:
        assert_can_edit_filter(g.user)
    except ForbiddenError as exc:
        return jsonify({"detail": str(exc)}), 403
    body = await request.get_json(force=True)
    try:
        picked = normalize_operators((body or {}).get("operators", []))
    except RuleError as exc:
        return jsonify({"detail": str(exc)}), 400
    async with SessionLocal() as session:
        row = await OperatorFilterRepo(session).save(picked, g.user.username)
        return _filter_json(row)


@app.route("/api/readings/spectrum")
async def spectrum():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        allowed = await OperatorFilterRepo(session).allowed_operators()
        rows = await ReadingRepo(session).recent(allowed, limit=24)
        return {"readings": [_reading_json(r) for r in rows]}


@app.route("/api/readings/ledger")
async def ledger():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        allowed = await OperatorFilterRepo(session).allowed_operators()
        rows = await ReadingRepo(session).recent(allowed, limit=500)
        return {"readings": [_reading_json(r) for r in rows]}
