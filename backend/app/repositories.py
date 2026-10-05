from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Filature, OperatorFilter, User, utcnow


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins).selectinload(Basin.readings)
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings))
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class OperatorFilterRepo:
    """采样人过滤的读写。只动 operator_filter 一行，绝不碰汤温记录。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> OperatorFilter | None:
        return await self.session.get(OperatorFilter, OperatorFilter.SINGLETON_ID)

    async def save(self, operators: list[str], username: str) -> OperatorFilter:
        last_error: IntegrityError | None = None
        for _ in range(3):
            row = await self.get()
            if row is None:
                row = OperatorFilter(id=OperatorFilter.SINGLETON_ID)
                self.session.add(row)
            row.operators = list(operators)
            row.updated_by = username
            row.updated_at = utcnow()
            try:
                await self.session.commit()
                return row
            except IntegrityError as exc:
                # 两名主管同时首写撞主键：回滚重试即转为更新，库里始终只留一版
                last_error = exc
                await self.session.rollback()
        raise last_error

    async def allowed_operators(self) -> set[str] | None:
        """None = 尚未保存过滤（不过滤）；集合 = 只放行这些操作人（空集 = 全不放行）。"""
        row = await self.get()
        if row is None:
            return None
        return set(row.operators or [])


class ReadingRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def operators(self) -> list[str]:
        result = await self.session.execute(
            select(BathReading.operator).distinct().order_by(BathReading.operator)
        )
        return [op for (op,) in result.all() if op]

    async def recent(
        self, allowed: set[str] | None, limit: int | None = None
    ) -> list[BathReading]:
        stmt = (
            select(BathReading)
            .options(selectinload(BathReading.basin))
            .order_by(BathReading.taken_at.desc(), BathReading.id.desc())
        )
        if allowed is not None:
            stmt = stmt.where(BathReading.operator.in_(allowed))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
