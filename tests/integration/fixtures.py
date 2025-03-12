from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest
from pytest_lazy_fixtures import lf

from sqlalchemy import URL, Engine, NullPool, create_engine, insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from strawberry.scalars import JSON
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import generate_query

from .models import Color, Fruit, User, metadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from pytest import FixtureRequest, MonkeyPatch
    from pytest_databases.docker.postgres import PostgresService

    from .typing import RawRecordData

__all__ = (
    "any_query",
    "async_engine",
    "async_session",
    "asyncpg_engine",
    "engine",
    "no_session_query",
    "psycopg_async_engine",
    "psycopg_engine",
    "raw_colors",
    "raw_fruits",
    "raw_users",
    "seed_db_async",
    "seed_db_sync",
    "session",
)

scalar_overrides: dict[object, Any] = {dict[str, Any]: JSON}


@pytest.fixture(autouse=True)
def _patch_base(monkeypatch: MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure new registry state for every test.

    This prevents errors such as "Table '...' is already defined for
    this MetaData instance...
    """
    from sqlalchemy.orm import DeclarativeBase

    from . import models

    class NewUUIDBase(models.BaseColumns, DeclarativeBase):
        __abstract__ = True

    monkeypatch.setattr(models, "UUIDBase", NewUUIDBase)


# Sync engines


@pytest.fixture
def psycopg_engine(postgres_service: PostgresService) -> Engine:
    """Postgresql instance for end-to-end testing."""
    return create_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=postgres_service.password,
            host=postgres_service.host,
            port=postgres_service.port,
            database=postgres_service.database,
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture(
    name="engine",
    params=[
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def engine(request: FixtureRequest) -> Engine:
    return cast(Engine, request.getfixturevalue(request.param))


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# Async engines


@pytest.fixture
def asyncpg_engine(postgres_service: PostgresService) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+asyncpg",
            username="postgres",
            password=postgres_service.password,
            host=postgres_service.host,
            port=postgres_service.port,
            database=postgres_service.database,
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture
def psycopg_async_engine(postgres_service: PostgresService) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=postgres_service.password,
            host=postgres_service.host,
            port=postgres_service.port,
            database=postgres_service.database,
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture(
    name="async_engine",
    params=[
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def async_engine(request: FixtureRequest) -> AsyncEngine:
    return cast(AsyncEngine, request.getfixturevalue(request.param))


@pytest.fixture
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session = async_sessionmaker(bind=async_engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


# Mock data


@pytest.fixture
def raw_colors() -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Red"},
        {"id": str(uuid4()), "name": "Yellow"},
        {"id": str(uuid4()), "name": "Orange"},
        {"id": str(uuid4()), "name": "Green"},
        {"id": str(uuid4()), "name": "Pink"},
    ]


@pytest.fixture
def raw_fruits(raw_colors: RawRecordData) -> RawRecordData:
    return [
        {
            "id": str(uuid4()),
            "name": "Apple",
            "color_id": raw_colors[0]["id"],
            "sweetness": 7,
            "has_core": True,
            "adjectives": ["crisp", "juicy", "sweet"],
            "price_decimal": Decimal("1.99"),
            "price_float": 1.99,
        },
        {
            "id": str(uuid4()),
            "name": "Banana",
            "color_id": raw_colors[1]["id"],
            "sweetness": 8,
            "has_core": False,
            "adjectives": ["soft", "sweet", "tropical"],
            "price_decimal": Decimal("0.89"),
            "price_float": 0.89,
        },
        {
            "id": str(uuid4()),
            "name": "Orange",
            "color_id": raw_colors[2]["id"],
            "sweetness": 6,
            "has_core": False,
            "adjectives": ["tangy", "juicy", "citrusy"],
            "price_decimal": Decimal("1.29"),
            "price_float": 1.29,
        },
        {
            "id": str(uuid4()),
            "name": "Strawberry",
            "color_id": raw_colors[3]["id"],
            "sweetness": 9,
            "has_core": False,
            "adjectives": ["sweet", "fragrant", "small"],
            "price_decimal": Decimal("2.49"),
            "price_float": 2.49,
        },
        {
            "id": str(uuid4()),
            "name": "Watermelon",
            "color_id": raw_colors[4]["id"],
            "sweetness": 8,
            "has_core": True,
            "adjectives": ["juicy", "refreshing", "summery"],
            "price_decimal": Decimal("4.99"),
            "price_float": 4.99,
        },
    ]


@pytest.fixture
def raw_users() -> RawRecordData:
    return [
        {
            "id": str(uuid4()),
            "name": "Alice",
            "settings": {"theme": "dark", "notifications": True},
            "birthday": date(1990, 5, 15),
            "newsletter_send_time": time(8, 0),
        },
        {
            "id": str(uuid4()),
            "name": "Bob",
            "settings": {"theme": "light", "notifications": False},
            "birthday": date(1985, 10, 22),
            "newsletter_send_time": time(9, 30),
        },
        {
            "id": str(uuid4()),
            "name": "Charlie",
            "settings": {"theme": "auto", "notifications": True},
            "birthday": date(1995, 3, 8),
            "newsletter_send_time": time(7, 15),
        },
    ]


@pytest.fixture
def seed_db_sync(
    engine: Engine, raw_fruits: RawRecordData, raw_colors: RawRecordData, raw_users: RawRecordData
) -> None:
    with engine.begin() as conn:
        metadata.drop_all(conn)
        metadata.create_all(conn)
        conn.execute(insert(Color).values(raw_colors))
        conn.execute(insert(Fruit).values(raw_fruits))
        conn.execute(insert(User).values(raw_users))


@pytest.fixture
async def seed_db_async(
    async_engine: AsyncEngine, raw_fruits: RawRecordData, raw_colors: RawRecordData, raw_users: RawRecordData
) -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        await conn.execute(insert(Color).values(raw_colors))
        await conn.execute(insert(Fruit).values(raw_fruits))
        await conn.execute(insert(User).values(raw_users))


@pytest.fixture(params=[lf("async_session"), lf("session")], ids=["async", "sync"])
def any_query(sync_query: type[Any], async_query: type[Any], request: FixtureRequest) -> AnyQueryExecutor:
    if isinstance(request.param, AsyncSession):
        request.getfixturevalue("seed_db_async")
        return generate_query(session=request.param, query=async_query, scalar_overrides=scalar_overrides)
    request.getfixturevalue("seed_db_sync")

    return generate_query(session=request.param, query=sync_query, scalar_overrides=scalar_overrides)


@pytest.fixture
def no_session_query(sync_query: type[Any]) -> SyncQueryExecutor:
    return generate_query(query=sync_query, scalar_overrides=scalar_overrides)
