from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from sqlalchemy import URL, Engine, NullPool, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from pytest import FixtureRequest, MonkeyPatch
    from pytest_databases.docker.postgres import PostgresService

__all__ = (
    "async_engine",
    "async_session",
    "asyncpg_engine",
    "engine",
    "psycopg_async_engine",
    "psycopg_engine",
    "session",
)


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
