from quart import Quart, g, jsonify, request
from quart.helpers import make_response

from app.db import SessionLocal
from app.models import Basin
from app.repositories import (
    BasinRepo,
    OperatorFilterRepo,
    ReadingRepo,
    StaleFilter,
    UserRepo,
)
from app.security import make_token, parse_token, verify_password
from app.services import (
    FilterError,
    RuleError,
    assert_can_set_status,
    latest_temp,
    normalize_selection,
    reading_json,
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


def require_admin():
    denied = require_user()
    if denied:
        return denied
    if g.user.role != "admin":
        return jsonify({"detail": "仅管理员可操作"}), 403
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


def _filter_json(row, candidates: list[dict] | None = None) -> dict:
    configured = row is not None and row.selected is not None
    return {
        "configured": configured,
        "version": row.version if row is not None else 0,
        "operators": list(row.selected) if configured else [],
        "candidates": candidates or [],
        "updatedBy": row.updated_by if row is not None else "",
        "updatedAt": row.updated_at.isoformat() if row is not None and row.updated_at else None,
    }


@app.route("/api/operators")
async def operators():
    """候选操作人（曾登记过汤温的人）。"""
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        return {"operators": await OperatorFilterRepo(session).candidates()}


@app.route("/api/operator-filter", methods=["GET"])
async def get_operator_filter():
    denied = require_admin()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = OperatorFilterRepo(session)
        row = await repo.get()
        return _filter_json(row, await repo.candidates())


@app.route("/api/operator-filter", methods=["PUT"])
async def put_operator_filter():
    denied = require_admin()
    if denied:
        return denied
    body = await request.get_json(force=True)
    async with SessionLocal() as session:
        repo = OperatorFilterRepo(session)
        candidate_names = {c["username"] for c in await repo.candidates()}
        try:
            expected_version = int((body or {}).get("version"))
        except (TypeError, ValueError):
            return jsonify({"detail": "缺少版本号 version"}), 400
        try:
            selected = normalize_selection(body, candidate_names)
        except FilterError as exc:
            return jsonify({"detail": str(exc)}), 400
        try:
            row = await repo.save(expected_version, selected, g.user.username)
        except StaleFilter:
            current = await repo.get()
            return (
                jsonify(
                    {
                        "detail": "勾选已被另一位主管抢先保存，请按库里留下的版本核对后再提交",
                        "current": _filter_json(current, await repo.candidates()),
                    }
                ),
                409,
            )
        return _filter_json(row, await repo.candidates())


async def _filtered_readings(session) -> tuple[bool, list[str], list]:
    """温谱与台账走同一处取数：同一批勾选、同一条查询。

    返回 (configured, selected, readings)。从未保存（configured=False）时
    selected 为空名单、readings 为全量；保存空名单时 readings 必为空。
    """
    repo = OperatorFilterRepo(session)
    row = await repo.get()
    configured = row is not None and row.selected is not None
    selected = list(row.selected) if configured else []
    readings = await ReadingRepo(session).filtered(selected if configured else None)
    return configured, selected, readings


@app.route("/api/temperature-profile")
async def temperature_profile():
    """环盆底下那条温谱：只画当前勾选版本里操作人的汤温点。"""
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        configured, selected, readings = await _filtered_readings(session)
        all_operators = [c["username"] for c in await OperatorFilterRepo(session).candidates()]
        return {
            "configured": configured,
            "operators": selected,
            "allOperators": all_operators,
            "points": [reading_json(r) for r in readings],
        }


@app.route("/api/readings/ledger")
async def readings_ledger():
    """温谱台账：与温谱同一批勾选，没勾中的人一行都不出现。"""
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        configured, selected, readings = await _filtered_readings(session)
        return {
            "configured": configured,
            "operators": selected,
            "rows": [reading_json(r) for r in readings],
        }
