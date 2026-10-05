"""缫丝盆门槛：标成已缫完须最近一次汤温落在 38～42℃。"""

from app.models import Basin

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


class ForbiddenError(PermissionError):
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


def assert_can_edit_filter(user) -> None:
    """采样人过滤只准管理员保存。"""
    if getattr(user, "role", "") != "admin":
        raise ForbiddenError("仅管理员可保存采样人过滤")


def normalize_operators(raw) -> list[str]:
    """清洗提交的勾选：去空白、去重、保序；不改任何已记下的汤温。"""
    if not isinstance(raw, list):
        raise RuleError("operators 必须是字符串数组")
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise RuleError("operators 必须是字符串数组")
        name = item.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out
