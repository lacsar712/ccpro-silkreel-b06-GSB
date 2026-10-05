from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, Filature, User, utcnow
from app.security import hash_password


async def _upsert_user(session, username: str, role: str) -> None:
    existing = await session.execute(select(User).where(User.username == username))
    user = existing.scalar_one_or_none()
    if user is None:
        session.add(
            User(username=username, password_hash=hash_password("123456"), role=role)
        )
    else:
        user.password_hash = hash_password("123456")
        user.role = role


async def seed_demo() -> None:
    async with SessionLocal() as session:
        await _upsert_user(session, "admin", "admin")
        await _upsert_user(session, "admin2", "admin")
        await _upsert_user(session, "worker", "worker")

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill:
            # 老数据卷：只补插更早的读数，绝不修改已记下的温度数字。
            existing_ops = (
                await session.execute(
                    select(BathReading.operator)
                    .where(BathReading.operator != "")
                    .distinct()
                )
            ).scalars().all()
            if not set(existing_ops) - {"worker"}:
                basins = {
                    b.code: b
                    for b in (
                        (
                            await session.execute(
                                select(Basin).where(Basin.filature_id == mill.id)
                            )
                        )
                        .scalars()
                        .all()
                    )
                }
                now = utcnow()
                backfill = [
                    ("甲-1", 38.9, "阿珍"),
                    ("乙-1", 41.6, "阿巧"),
                    ("乙-2", 39.8, "阿珍"),
                    ("丙-2", 37.5, "阿巧"),
                ]
                for code, temp, op in backfill:
                    basin = basins.get(code)
                    if basin is None:
                        continue
                    already = (
                        await session.execute(
                            select(BathReading).where(
                                BathReading.basin_id == basin.id,
                                BathReading.operator == op,
                                BathReading.water_temp_c == temp,
                            )
                        )
                    ).scalar_one_or_none()
                    if already is None:
                        session.add(
                            BathReading(
                                basin_id=basin.id,
                                water_temp_c=temp,
                                operator=op,
                                taken_at=now - timedelta(hours=5),
                            )
                        )
            await session.commit()
            return

        mill = Filature(name="江口缫丝坞", riverside="东津渡")
        session.add(mill)
        await session.flush()
        now = utcnow()
        # 每条：盆号, 状态, 最近温度（决定状态门槛，数字保持不变）, 环位,
        # 更早一条读数的 (温度, 操作人)，让多名采样人在温谱上有点可被勾掉。
        specs = [
            ("甲-1", Basin.STATUS_REELING, 40.5, 0, (38.9, "阿珍")),
            ("甲-2", Basin.STATUS_SOAKING, None, 1, None),
            ("乙-1", Basin.STATUS_REELED, 39.2, 2, (41.6, "阿巧")),
            ("乙-2", Basin.STATUS_REELING, 36.0, 3, (39.8, "阿珍")),
            ("丙-1", Basin.STATUS_SOAKING, None, 4, None),
            ("丙-2", Basin.STATUS_REELED, 41.0, 5, (37.5, "阿巧")),
        ]
        for code, status, temp, idx, earlier in specs:
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
            session.add(basin)
            await session.flush()
            if temp is not None:
                if earlier is not None:
                    earlier_temp, earlier_op = earlier
                    session.add(
                        BathReading(
                            basin_id=basin.id,
                            water_temp_c=earlier_temp,
                            operator=earlier_op,
                            taken_at=now - timedelta(hours=5),
                        )
                    )
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator="worker",
                        taken_at=now - timedelta(hours=2),
                    )
                )
        await session.commit()
