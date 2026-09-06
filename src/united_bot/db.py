from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .domain import Match, MatchStatus, Prediction, Score


class Base(DeclarativeBase):
    pass


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(Integer, index=True)
    home_team: Mapped[str] = mapped_column(String(120))
    away_team: Mapped[str] = mapped_column(String(120))
    competition: Mapped[str] = mapped_column(String(120))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.SCHEDULED.value)
    final_home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PredictionRow(Base):
    __tablename__ = "predictions"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnnouncementRow(Base):
    __tablename__ = "announcements"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    announcement_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def match_row_to_domain(row: MatchRow) -> Match:
    kickoff_at = row.kickoff_at
    if kickoff_at.tzinfo is None:
        kickoff_at = kickoff_at.replace(tzinfo=timezone.utc)
    final_score = (
        Score(row.final_home_score, row.final_away_score)
        if row.final_home_score is not None and row.final_away_score is not None
        else None
    )
    return Match(
        id=row.id,
        guild_id=row.guild_id,
        home_team=row.home_team,
        away_team=row.away_team,
        competition=row.competition,
        kickoff_at=kickoff_at,
        status=MatchStatus(row.status),
        final_score=final_score,
    )


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, connect_args={"timeout": 5})

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(session_factory: async_sessionmaker[AsyncSession]) -> None:
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class MatchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, match: Match) -> Match:
        async with self._session_factory() as session:
            row = MatchRow(
                guild_id=match.guild_id,
                home_team=match.home_team,
                away_team=match.away_team,
                competition=match.competition,
                kickoff_at=match.kickoff_at,
                status=match.status.value,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def get(self, match_id: int, guild_id: int) -> Match | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(MatchRow).where(MatchRow.id == match_id, MatchRow.guild_id == guild_id)
            )
            return self._to_domain(row) if row else None

    async def get_current(self, guild_id: int, now: datetime) -> Match | None:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(MatchRow)
                    .where(
                        MatchRow.guild_id == guild_id,
                        MatchRow.status == MatchStatus.SCHEDULED.value,
                        MatchRow.kickoff_at > now,
                        MatchRow.kickoff_at <= now + timedelta(days=3),
                    )
                    .order_by(MatchRow.kickoff_at)
                )
            ).all()
            for row in rows:
                match = self._to_domain(row)
                if match.can_predict(now):
                    return match
            return None

    async def get_in_progress(self, guild_id: int, now: datetime) -> Match | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(MatchRow)
                .where(
                    MatchRow.guild_id == guild_id,
                    MatchRow.status == MatchStatus.SCHEDULED.value,
                    MatchRow.kickoff_at <= now,
                )
                .order_by(MatchRow.kickoff_at.desc())
                .limit(1)
            )
            return self._to_domain(row) if row else None

    async def get_next_scheduled(self, guild_id: int) -> Match | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(MatchRow)
                .where(
                    MatchRow.guild_id == guild_id,
                    MatchRow.status == MatchStatus.SCHEDULED.value,
                )
                .order_by(MatchRow.kickoff_at)
            )
            return self._to_domain(row) if row else None

    async def list_prediction_open_due(self, now: datetime) -> list[Match]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(MatchRow)
                    .where(
                        MatchRow.status == MatchStatus.SCHEDULED.value,
                        MatchRow.kickoff_at > now,
                        MatchRow.kickoff_at <= now + timedelta(days=3),
                    )
                    .order_by(MatchRow.kickoff_at)
                )
            ).all()
            return [self._to_domain(row) for row in rows]

    async def update(self, match: Match) -> Match:
        if match.id is None:
            raise ValueError("Nie można aktualizować meczu bez identyfikatora.")
        async with self._session_factory() as session:
            row = await session.get(MatchRow, match.id)
            if row is None or row.guild_id != match.guild_id:
                raise LookupError("Nie znaleziono meczu.")
            row.kickoff_at = match.kickoff_at
            row.status = match.status.value
            row.final_home_score = match.final_score.home if match.final_score else None
            row.final_away_score = match.final_score.away if match.final_score else None
            await session.commit()
            return self._to_domain(row)

    @staticmethod
    def _to_domain(row: MatchRow) -> Match:
        return match_row_to_domain(row)


class PredictionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(self, prediction: Prediction) -> Prediction:
        async with self._session_factory() as session:
            row = await session.get(
                PredictionRow,
                {"match_id": prediction.match_id, "user_id": prediction.user_id},
            )
            if row is None:
                row = PredictionRow(
                    match_id=prediction.match_id,
                    user_id=prediction.user_id,
                    home_score=prediction.score.home,
                    away_score=prediction.score.away,
                    points=prediction.points,
                    submitted_at=prediction.submitted_at or prediction.updated_at,
                    updated_at=prediction.updated_at,
                )
                session.add(row)
            else:
                row.home_score = prediction.score.home
                row.away_score = prediction.score.away
                row.points = prediction.points
                row.submitted_at = prediction.updated_at
                row.updated_at = prediction.updated_at
            await session.commit()
            return self._to_domain(row)

    async def get(self, match_id: int, user_id: int) -> Prediction | None:
        async with self._session_factory() as session:
            row = await session.get(
                PredictionRow,
                {"match_id": match_id, "user_id": user_id},
            )
            return self._to_domain(row) if row else None

    async def get_latest_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> tuple[Match, Prediction] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MatchRow, PredictionRow)
                .join(PredictionRow, PredictionRow.match_id == MatchRow.id)
                .where(
                    MatchRow.guild_id == guild_id,
                    MatchRow.status == MatchStatus.FINISHED.value,
                    PredictionRow.user_id == user_id,
                )
                .order_by(MatchRow.kickoff_at.desc())
                .limit(1)
            )
            row = result.one_or_none()
            if row is None:
                return None
            match_row, prediction_row = row
            return match_row_to_domain(match_row), self._to_domain(prediction_row)

    async def has_any_for_user(self, guild_id: int, user_id: int) -> bool:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PredictionRow.match_id)
                .join(MatchRow, MatchRow.id == PredictionRow.match_id)
                .where(
                    MatchRow.guild_id == guild_id,
                    PredictionRow.user_id == user_id,
                )
                .limit(1)
            )
            return row is not None

    async def settle_match(self, match_id: int, actual: Score) -> list[Prediction]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(PredictionRow).where(PredictionRow.match_id == match_id)
                )
            ).all()
            for row in rows:
                row.points = calculate_points_from_rows(actual, row)
            await session.commit()
            return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: PredictionRow) -> Prediction:
        return Prediction(
            match_id=row.match_id,
            user_id=row.user_id,
            score=Score(row.home_score, row.away_score),
            points=row.points,
            submitted_at=row.submitted_at or row.updated_at,
            updated_at=row.updated_at,
        )


class AnnouncementRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def was_sent(self, match_id: int, announcement_type: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(
                AnnouncementRow,
                {"match_id": match_id, "announcement_type": announcement_type},
            )
            return row is not None

    async def mark_sent(
        self,
        match_id: int,
        announcement_type: str,
        sent_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                AnnouncementRow(
                    match_id=match_id,
                    announcement_type=announcement_type,
                    sent_at=sent_at,
                )
            )
            await session.commit()


def calculate_points_from_rows(actual: Score, prediction: PredictionRow) -> int:
    from .domain import calculate_prediction_points

    return calculate_prediction_points(
        actual,
        Score(prediction.home_score, prediction.away_score),
    )
