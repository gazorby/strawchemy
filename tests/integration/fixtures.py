from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest
import sqlparse
from geoalchemy2 import WKBElement, WKTElement
from pytest_lazy_fixtures import lf
from strawchemy.strawberry.geo import GeoJSON

from sqlalchemy import URL, Engine, Executable, Insert, MetaData, NullPool, create_engine, insert
from sqlalchemy.event import listens_for
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker
from strawberry.scalars import JSON
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import generate_query

from .models import Color, Fruit, SQLDataTypes, SQLDataTypesContainer, User, metadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from pytest import FixtureRequest, MonkeyPatch
    from pytest_databases.docker.postgres import PostgresService
    from strawchemy.sqlalchemy.typing import AnySession

    from .typing import RawRecordData

__all__ = (
    "QueryTracker",
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

scalar_overrides: dict[object, Any] = {dict[str, Any]: JSON, WKTElement: GeoJSON, WKBElement: GeoJSON}


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


@pytest.fixture
def database_service(postgres_service: PostgresService) -> PostgresService:
    return postgres_service


# Sync engines


@pytest.fixture
def psycopg_engine(database_service: PostgresService) -> Engine:
    """Postgresql instance for end-to-end testing."""
    return create_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=database_service.password,
            host=database_service.host,
            port=database_service.port,
            database=database_service.database,
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
def asyncpg_engine(database_service: PostgresService) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+asyncpg",
            username="postgres",
            password=database_service.password,
            host=database_service.host,
            port=database_service.port,
            database=database_service.database,
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture
def psycopg_async_engine(database_service: PostgresService) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=database_service.password,
            host=database_service.host,
            port=database_service.port,
            database=database_service.database,
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
            "adjectives": ["crisp", "juicy", "sweet"],
        },
        {
            "id": str(uuid4()),
            "name": "Banana",
            "color_id": raw_colors[1]["id"],
            "adjectives": ["soft", "sweet", "tropical"],
        },
        {
            "id": str(uuid4()),
            "name": "Orange",
            "color_id": raw_colors[2]["id"],
            "adjectives": ["tangy", "juicy", "citrusy"],
        },
        {
            "id": str(uuid4()),
            "name": "Strawberry",
            "color_id": raw_colors[3]["id"],
            "adjectives": ["sweet", "fragrant", "small"],
        },
        {
            "id": str(uuid4()),
            "name": "Watermelon",
            "color_id": raw_colors[4]["id"],
            "adjectives": ["juicy", "refreshing", "summery"],
        },
    ]


@pytest.fixture
def raw_users() -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Alice"},
        {"id": str(uuid4()), "name": "Bob"},
        {"id": str(uuid4()), "name": "Charlie"},
    ]


@pytest.fixture
def raw_sql_data_types_container() -> RawRecordData:
    return [{"id": str(uuid4())}]


@pytest.fixture
def raw_sql_data_types(raw_sql_data_types_container: RawRecordData) -> RawRecordData:
    return [
        # Standard case with typical values
        {
            "id": str(uuid4()),
            "date_col": date(2023, 1, 15),
            "time_col": time(14, 30, 45),
            "time_delta_col": time(23, 59, 59),
            "datetime_col": datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC),
            "str_col": "test string",
            "int_col": 42,
            "float_col": 3.14159,
            "decimal_col": Decimal("123.45"),
            "bool_col": True,
            "uuid_col": uuid4(),
            "dict_col": {"key1": "value1", "key2": 2, "nested": {"inner": "value"}},
            "array_str_col": ["one", "two", "three"],
            "optional_str_col": "optional string",
            "container_id": raw_sql_data_types_container[0]["id"],
        },
        # Case with negative numbers and different values
        {
            "id": str(uuid4()),
            "date_col": date(2022, 12, 31),
            "time_col": time(8, 15, 0),
            "time_delta_col": time(12, 0, 0),
            "datetime_col": datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC),
            "str_col": "another string",
            "int_col": -10,
            "float_col": 2.71828,
            "decimal_col": Decimal("-99.99"),
            "bool_col": False,
            "uuid_col": uuid4(),
            "dict_col": {"status": "pending", "count": 0},
            "array_str_col": ["apple", "banana", "cherry", "date"],
            "optional_str_col": "another optional string",
            "container_id": raw_sql_data_types_container[0]["id"],
        },
        # Edge case with empty values
        {
            "id": str(uuid4()),
            "date_col": date(2024, 2, 29),  # leap year
            "time_col": time(0, 0, 0),
            "time_delta_col": time(1, 1, 1),
            "datetime_col": datetime(2024, 2, 29, 0, 0, 0, tzinfo=UTC),
            "str_col": "",  # empty string
            "int_col": 0,
            "float_col": 0.0,
            "decimal_col": Decimal("0.00"),
            "bool_col": False,
            "uuid_col": uuid4(),
            "dict_col": {},  # empty dict
            "array_str_col": [],  # empty array
            "optional_str_col": None,
            "container_id": raw_sql_data_types_container[0]["id"],
        },
    ]


@pytest.fixture
def seed_insert_statements(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    raw_users: RawRecordData,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
) -> list[Insert]:
    return [
        insert(Color).values(raw_colors),
        insert(Fruit).values(raw_fruits),
        insert(User).values(raw_users),
        insert(SQLDataTypesContainer).values(raw_sql_data_types_container),
        insert(SQLDataTypes).values(raw_sql_data_types),
    ]


@pytest.fixture
def before_create_all_statements() -> list[Executable]:
    return []


@pytest.fixture(name="metadata")
def fx_metadata() -> MetaData:
    return metadata


@pytest.fixture
def seed_db_sync(
    engine: Engine,
    metadata: MetaData,
    seed_insert_statements: list[Insert],
    before_create_all_statements: list[Executable],
) -> None:
    with engine.begin() as conn:
        for statement in before_create_all_statements:
            conn.execute(statement)
        metadata.drop_all(conn)
        metadata.create_all(conn)
        for statement in seed_insert_statements:
            conn.execute(statement)


@pytest.fixture
async def seed_db_async(
    async_engine: AsyncEngine,
    metadata: MetaData,
    seed_insert_statements: list[Insert],
    before_create_all_statements: list[Executable],
) -> None:
    async with async_engine.begin() as conn:
        for statement in before_create_all_statements:
            await conn.execute(statement)
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        for statement in seed_insert_statements:
            await conn.execute(statement)


@pytest.fixture(params=[lf("async_session"), lf("session")], ids=["async", "sync"])
def any_session(request: FixtureRequest) -> AnySession:
    return request.param


@pytest.fixture(params=[lf("any_session")], ids=["tracked"])
def query_tracker(request: FixtureRequest) -> QueryTracker:
    return QueryTracker(request.param)


@pytest.fixture(params=[lf("any_session")], ids=["session"])
def any_query(sync_query: type[Any], async_query: type[Any], request: FixtureRequest) -> AnyQueryExecutor:
    if isinstance(request.param, AsyncSession):
        request.getfixturevalue("seed_db_async")
        return generate_query(session=request.param, query=async_query, scalar_overrides=scalar_overrides)
    request.getfixturevalue("seed_db_sync")

    return generate_query(session=request.param, query=sync_query, scalar_overrides=scalar_overrides)


@pytest.fixture
def no_session_query(sync_query: type[Any]) -> SyncQueryExecutor:
    return generate_query(query=sync_query, scalar_overrides=scalar_overrides)


@dataclass
class StatementInspector:
    state: ORMExecuteState

    @property
    def statement_str(self) -> str:
        return str(self.state.statement)

    @property
    def statement_formatted(self) -> str:
        return sqlparse.format(self.statement_str, reindent=True, use_space_around_operators=True, keyword_case="upper")


@dataclass
class QueryTracker:
    session: AnySession

    executions: list[StatementInspector] = dataclasses.field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.session, AsyncSession):
            listens_for(self.session.sync_session, "do_orm_execute")(self._event_listener)
        else:
            listens_for(self.session, "do_orm_execute")(self._event_listener)

    def _event_listener(self, orm_execute_state: ORMExecuteState) -> None:
        self.executions.append(StatementInspector(orm_execute_state))

    @property
    def query_count(self) -> int:
        return len(self.executions)

    def __getitem__(self, index: int) -> StatementInspector:
        return self.executions[index]
