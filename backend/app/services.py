"""缫丝盆门槛：标成已缫完须最近一次汤温落在 38～42℃。"""

from app.models import Basin, BathReading

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )


class FilterError(ValueError):
    pass


def normalize_selection(body: object, candidate_ops: set[str]) -> list[str]:
    """校验并规范化勾选名单。

    必须是字符串数组；只接受实际存在的操作人；去重并保持稳定顺序。
    空数组合法——意思是「一个都不勾」，温谱台账两边都空。
    """
    if not isinstance(body, dict) or "operators" not in body:
        raise FilterError("缺少 operators 勾选名单")
    raw = body.get("operators")
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise FilterError("operators 必须是字符串数组")
    seen: set[str] = set()
    selected: list[str] = []
    for name in raw:
        if name in seen:
            continue
        if name not in candidate_ops:
            raise FilterError(f"未知操作人：{name}")
        seen.add(name)
        selected.append(name)
    return selected


def reading_json(reading: BathReading) -> dict:
    return {
        "id": reading.id,
        "basinId": reading.basin_id,
        "basinCode": reading.basin.code if reading.basin else "",
        "operator": reading.operator,
        "waterTempC": reading.water_temp_c,
        "takenAt": reading.taken_at.isoformat() if reading.taken_at else None,
    }
