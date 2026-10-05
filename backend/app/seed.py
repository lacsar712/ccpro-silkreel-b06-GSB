from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Basin, BathReading, Filature, User, utcnow
from app.security import hash_password


async def seed_demo() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).where(User.username == "admin"))
        admin = existing.scalar_one_or_none()
        if admin is None:
            admin = User(username="admin", password_hash=hash_password("123456"), role="admin")
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        existing_w = await session.execute(select(User).where(User.username == "worker"))
        worker = existing_w.scalar_one_or_none()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        mill = (await session.execute(select(Filature))).scalars().first()
        if mill:
            await session.commit()
            return

        mill = Filature(name="江口缫丝坞", riverside="东津渡")
        session.add(mill)
        await session.flush()
        now = utcnow()
        # (汤温, 操作人, 几小时前)；每盆最近一条保持 worker 原值不动，
        # admin 的记录更早，只用于让采样人过滤有多人可勾。
        specs = [
            ("甲-1", Basin.STATUS_REELING, 0, [(40.5, "worker", 2), (39.6, "admin", 5)]),
            ("甲-2", Basin.STATUS_SOAKING, 1, []),
            ("乙-1", Basin.STATUS_REELED, 2, [(39.2, "worker", 2), (38.4, "admin", 6)]),
            ("乙-2", Basin.STATUS_REELING, 3, [(36.0, "worker", 2), (35.5, "admin", 5)]),
            ("丙-1", Basin.STATUS_SOAKING, 4, []),
            ("丙-2", Basin.STATUS_REELED, 5, [(41.0, "worker", 2), (40.8, "admin", 6)]),
        ]
        for code, status, idx, readings in specs:
            basin = Basin(filature_id=mill.id, code=code, status=status, ring_index=idx)
            session.add(basin)
            await session.flush()
            for temp, operator, hours_ago in readings:
                session.add(
                    BathReading(
                        basin_id=basin.id,
                        water_temp_c=temp,
                        operator=operator,
                        taken_at=now - timedelta(hours=hours_ago),
                    )
                )
        await session.commit()
