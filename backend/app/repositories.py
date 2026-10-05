from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    SINGLETON_ID = 1

    def __init__(self, session: AsyncSession):
        self.session = session

    async def candidates(self) -> list[dict]:
        """所有曾记下汤温的操作人（温谱与台账上可能出现的人）。"""
        result = await self.session.execute(
            select(BathReading.operator, func.count(BathReading.id))
            .where(BathReading.operator != "")
            .group_by(BathReading.operator)
            .order_by(BathReading.operator)
        )
        return [{"username": op, "readingCount": count} for op, count in result.all()]

    async def get(self) -> OperatorFilter | None:
        result = await self.session.execute(
            select(OperatorFilter).where(OperatorFilter.singleton_id == self.SINGLETON_ID)
        )
        return result.scalar_one_or_none()

    async def save(
        self, expected_version: int, selected: list[str], username: str
    ) -> OperatorFilter:
        """以乐观锁保存勾选。成功返回新行；版本不符抛 StaleFilter。

        两名主管同时提交时只有一人能写中：已有行时 UPDATE 带
        version==expected 条件；首次提交（expected_version==0）走
        ON CONFLICT DO NOTHING 的插入，另一个首次提交因冲突而失败。
        库里始终只留一版。
        """
        if expected_version == 0:
            result = await self.session.execute(
                pg_insert(OperatorFilter)
                .values(
                    singleton_id=self.SINGLETON_ID,
                    selected=selected,
                    version=1,
                    updated_by=username,
                    updated_at=utcnow(),
                )
                .on_conflict_do_nothing(index_elements=[OperatorFilter.singleton_id])
                .returning(OperatorFilter.singleton_id)
            )
            if result.scalar_one_or_none() is None:
                await self.session.rollback()
                raise StaleFilter()
        else:
            result = await self.session.execute(
                update(OperatorFilter)
                .where(
                    OperatorFilter.singleton_id == self.SINGLETON_ID,
                    OperatorFilter.version == expected_version,
                )
                .values(
                    selected=selected,
                    version=expected_version + 1,
                    updated_by=username,
                    updated_at=utcnow(),
                )
                .returning(OperatorFilter.version)
            )
            if result.scalar_one_or_none() is None:
                await self.session.rollback()
                raise StaleFilter()
        await self.session.commit()
        return await self.get()


class StaleFilter(Exception):
    """勾选版本已被别人抢先保存。"""


class ReadingRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def filtered(self, operators: list[str] | None) -> list[BathReading]:
        """温谱与台账共用的同一条查询：只取被勾中操作人的读数。

        operators 为 None 表示从未配置（全员）；空列表表示「一个都不勾」，
        直接返回空列表——不造任何行。
        """
        if operators is not None and not operators:
            return []
        stmt = (
            select(BathReading)
            .options(selectinload(BathReading.basin))
            .order_by(BathReading.taken_at, BathReading.id)
        )
        if operators:
            stmt = stmt.where(BathReading.operator.in_(operators))
        return list((await self.session.execute(stmt)).scalars().all())
