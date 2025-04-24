from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Literal, Self, TypeAlias, cast
from uuid import uuid4

import pytest
import sqlparse
from pytest_databases.docker.postgres import _provide_postgres_service
from pytest_lazy_fixtures import lf
from strawchemy.strawberry.scalars import Interval

from sqlalchemy import (
    URL,
    ClauseElement,
    Compiled,
    Connection,
    CursorResult,
    Delete,
    Dialect,
    Engine,
    Executable,
    Insert,
    MetaData,
    NullPool,
    Select,
    Update,
    create_engine,
    insert,
)
from sqlalchemy.event import listens_for
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from strawberry.scalars import JSON
from tests.fixtures import DefaultQuery
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import generate_query

from .models import Color, Fruit, FruitFarm, Group, SQLDataTypes, SQLDataTypesContainer, Topic, User, metadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterator

    from pytest import FixtureRequest, MonkeyPatch
    from pytest_databases._service import DockerService  # pyright: ignore[reportPrivateImportUsage]
    from pytest_databases.docker.postgres import PostgresService
    from pytest_databases.types import XdistIsolationLevel
    from strawchemy.sqlalchemy.typing import AnySession

    from syrupy.assertion import SnapshotAssertion

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
    "raw_sql_data_types",
    "raw_sql_data_types_set1",
    "raw_sql_data_types_set2",
    "raw_users",
    "seed_db_async",
    "seed_db_sync",
    "session",
)

FilterableStatement: TypeAlias = Literal["insert", "update", "select", "delete"]
scalar_overrides: dict[object, Any] = {dict[str, Any]: JSON, timedelta: Interval}

if find_spec("geoalchemy2") is not None:
    from strawchemy.strawberry.geo import GEO_SCALAR_OVERRIDES

    scalar_overrides |= GEO_SCALAR_OVERRIDES


GEO_DATA = [
    # Complete record with all geometry types
    {
        "id": str(uuid4()),
        "point_required": "POINT(0 0)",  # Origin point
        "point": "POINT(1 1)",  # Simple point
        "line_string": "LINESTRING(0 0, 1 1, 2 2)",  # Simple line with 3 points
        "polygon": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",  # Simple square
        "multi_point": "MULTIPOINT((0 0), (1 1), (2 2))",  # 3 points
        "multi_line_string": "MULTILINESTRING((0 0, 1 1), (2 2, 3 3))",  # 2 lines
        "multi_polygon": "MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)), ((2 2, 2 3, 3 3, 3 2, 2 2)))",  # 2 squares
        "geometry": "POINT(5 5)",  # Using point as generic geometry
    },
    # Record with only required fields
    {
        "id": str(uuid4()),
        "point_required": "POINT(10 20)",  # Required point
        "point": None,
        "line_string": None,
        "polygon": None,
        "multi_point": None,
        "multi_line_string": None,
        "multi_polygon": None,
        "geometry": None,
    },
    # Record with complex geometries
    {
        "id": str(uuid4()),
        "point_required": "POINT(45.5 -122.6)",  # Real-world coordinates (Portland, OR)
        "point": "POINT(-74.0060 40.7128)",  # New York City
        "line_string": "LINESTRING(-122.4194 37.7749, -118.2437 34.0522, -74.0060 40.7128)",  # SF to LA to NYC
        "polygon": "POLYGON((-122.4194 37.7749, -122.4194 37.8, -122.4 37.8, -122.4 37.7749, -122.4194 37.7749))",  # Area in SF
        "multi_point": "MULTIPOINT((-122.4194 37.7749), (-118.2437 34.0522), (-74.0060 40.7128))",  # Major US cities
        "multi_line_string": "MULTILINESTRING((-122.4194 37.7749, -118.2437 34.0522), (-118.2437 34.0522, -74.0060 40.7128))",  # Route segments
        "multi_polygon": "MULTIPOLYGON(((-122.42 37.78, -122.42 37.8, -122.4 37.8, -122.4 37.78, -122.42 37.78)), ((-118.25 34.05, -118.25 34.06, -118.24 34.06, -118.24 34.05, -118.25 34.05)))",  # Areas in SF and LA
        "geometry": "LINESTRING(-122.4194 37.7749, -74.0060 40.7128)",  # Direct SF to NYC
    },
    # Record with different geometry types
    {
        "id": str(uuid4()),
        "point_required": "POINT(100 200)",
        "point": "POINT(200 300)",
        "line_string": "LINESTRING(100 100, 200 200, 300 300, 400 400)",  # Longer line
        "polygon": "POLYGON((0 0, 0 10, 10 10, 10 0, 0 0), (2 2, 2 8, 8 8, 8 2, 2 2))",  # Polygon with hole
        "multi_point": "MULTIPOINT((10 10), (20 20), (30 30), (40 40), (50 50))",  # 5 points
        "multi_line_string": "MULTILINESTRING((10 10, 20 20), (30 30, 40 40), (50 50, 60 60))",  # 3 lines
        "multi_polygon": "MULTIPOLYGON(((0 0, 0 5, 5 5, 5 0, 0 0)), ((10 10, 10 15, 15 15, 15 10, 10 10)), ((20 20, 20 25, 25 25, 25 20, 20 20)))",  # 3 squares
        "geometry": "POLYGON((100 100, 100 200, 200 200, 200 100, 100 100))",  # Using polygon as geometry
    },
]


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


@pytest.fixture(autouse=False, scope="session")
def postgis_service(
    docker_service: DockerService, xdist_postgres_isolation_level: XdistIsolationLevel
) -> Generator[PostgresService, None, None]:
    with _provide_postgres_service(
        docker_service,
        image="postgis/postgis:17-3.5",
        name="postgis-17",
        xdist_postgres_isolate=xdist_postgres_isolation_level,
    ) as service:
        yield service


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
def raw_topics(raw_groups: RawRecordData) -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Hello!", "group_id": raw_groups[0]["id"]},
        {"id": str(uuid4()), "name": "Problems", "group_id": raw_groups[1]["id"]},
        {"id": str(uuid4()), "name": "Solution", "group_id": raw_groups[2]["id"]},
        {"id": str(uuid4()), "name": "How bake bread?", "group_id": raw_groups[3]["id"]},
        {"id": str(uuid4()), "name": "My new basement!", "group_id": raw_groups[4]["id"]},
    ]


@pytest.fixture
def raw_farms(raw_fruits: RawRecordData) -> RawRecordData:
    return [{"id": str(uuid4()), "name": f"{fruit['name']} farm", "fruit_id": fruit["id"]} for fruit in raw_fruits]


@pytest.fixture
def raw_groups() -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Group 1"},
        {"id": str(uuid4()), "name": "Group 2"},
        {"id": str(uuid4()), "name": "Group 3"},
        {"id": str(uuid4()), "name": "Group 4"},
        {"id": str(uuid4()), "name": "Group 5"},
    ]


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
def raw_users(raw_groups: RawRecordData) -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Alice", "group_id": raw_groups[0]["id"]},
        {"id": str(uuid4()), "name": "Bob", "group_id": None},
        {"id": str(uuid4()), "name": "Charlie", "group_id": None},
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
            "time_delta_col": timedelta(days=2, hours=23, minutes=59, seconds=59),
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
            "time_delta_col": timedelta(weeks=1, days=3, hours=12),
            "datetime_col": datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC),
            "str_col": "another STRING",
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
            "time_delta_col": timedelta(microseconds=500000, seconds=1),
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
def raw_sql_data_types_set1(raw_containers: RawRecordData) -> RawRecordData:
    return [
        # First set with moderate values
        {
            "id": str(uuid4()),
            "date_col": date(2021, 6, 15),
            "time_col": time(10, 45, 30),
            "time_delta_col": timedelta(days=-5, hours=18, minutes=30, seconds=15),
            "datetime_col": datetime(2021, 6, 15, 10, 45, 30, tzinfo=UTC),
            "str_col": "data set 1 string",
            "int_col": 100,
            "float_col": 5.5,
            "decimal_col": Decimal("50.75"),
            "bool_col": True,
            "uuid_col": uuid4(),
            "dict_col": {"category": "electronics", "price": 299.99},
            "array_str_col": ["red", "green", "blue"],
            "optional_str_col": "set1 optional",
            "container_id": raw_containers[0]["id"],
        },
        # Second entry with different values
        {
            "id": str(uuid4()),
            "date_col": date(2021, 7, 20),
            "time_col": time(15, 20, 10),
            "time_delta_col": timedelta(weeks=2, hours=9, minutes=45, seconds=30, microseconds=123456),
            "datetime_col": datetime(2021, 7, 20, 15, 20, 10, tzinfo=UTC),
            "str_col": "another set 1 string",
            "int_col": 75,
            "float_col": 7.25,
            "decimal_col": Decimal("75.50"),
            "bool_col": False,
            "uuid_col": uuid4(),
            "dict_col": {"category": "clothing", "price": 49.99, "size": "medium"},
            "array_str_col": ["circle", "square", "triangle"],
            "optional_str_col": "set1 optional",
            "container_id": raw_containers[0]["id"],
        },
    ]


@pytest.fixture
def raw_sql_data_types_set2(raw_containers: RawRecordData) -> RawRecordData:
    return [
        # First entry with moderate values
        {
            "id": str(uuid4()),
            "date_col": date(2020, 3, 10),
            "time_col": time(9, 15, 25),
            "time_delta_col": timedelta(days=30, hours=16, minutes=45),
            "datetime_col": datetime(2020, 3, 10, 9, 15, 25, tzinfo=UTC),
            "str_col": "data set 2 string",
            "int_col": 250,
            "float_col": 9.8,
            "decimal_col": Decimal("199.99"),
            "bool_col": True,
            "uuid_col": uuid4(),
            "dict_col": {"category": "furniture", "price": 599.99, "color": "brown"},
            "array_str_col": ["monday", "wednesday", "friday"],
            "optional_str_col": "set2 optional",
            "container_id": raw_containers[1]["id"],
        },
        # Second entry with different values
        {
            "id": str(uuid4()),
            "date_col": date(2020, 9, 5),
            "time_col": time(13, 0, 0),
            "time_delta_col": timedelta(days=-10, hours=-5, minutes=15, seconds=45, microseconds=999999),
            "datetime_col": datetime(2020, 9, 5, 13, 0, 0, tzinfo=UTC),
            "str_col": "another set 2 string",
            "int_col": 180,
            "float_col": 12.34,
            "decimal_col": Decimal("150.25"),
            "bool_col": False,
            "uuid_col": uuid4(),
            "dict_col": {"category": "books", "price": 24.99, "author": "John Doe"},
            "array_str_col": ["cat", "dog", "bird", "fish"],
            "optional_str_col": "another set2 optional",
            "container_id": raw_containers[1]["id"],
        },
    ]


@pytest.fixture
def raw_geo() -> RawRecordData:
    return GEO_DATA


# DB Seeding


@pytest.fixture
def seed_insert_statements(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    raw_users: RawRecordData,
    raw_farms: RawRecordData,
    raw_groups: RawRecordData,
    raw_topics: RawRecordData,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
) -> list[Insert]:
    return [
        insert(Group).values(raw_groups),
        insert(Topic).values(raw_topics),
        insert(Color).values(raw_colors),
        insert(Fruit).values(raw_fruits),
        insert(FruitFarm).values(raw_farms),
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


# Utilities


@pytest.fixture
def async_query() -> type[DefaultQuery]:
    return DefaultQuery


@pytest.fixture
def async_mutation() -> type[Any] | None:
    return None


@pytest.fixture
def sync_mutation() -> type[Any] | None:
    return None


@pytest.fixture(params=[lf("async_session"), lf("session")], ids=["async", "sync"])
def any_session(request: FixtureRequest) -> AnySession:
    return request.param


@pytest.fixture(params=[lf("any_session")], ids=["tracked"])
def query_tracker(request: FixtureRequest) -> QueryTracker:
    return QueryTracker(request.param)


@pytest.fixture(params=[lf("any_session")], ids=["session"])
def any_query(
    sync_query: type[Any],
    async_query: type[Any],
    async_mutation: type[Any] | None,
    sync_mutation: type[Any] | None,
    request: FixtureRequest,
) -> AnyQueryExecutor:
    if isinstance(request.param, AsyncSession):
        request.getfixturevalue("seed_db_async")
        return generate_query(
            session=request.param, query=async_query, mutation=async_mutation, scalar_overrides=scalar_overrides
        )
    request.getfixturevalue("seed_db_sync")

    return generate_query(
        session=request.param, query=sync_query, mutation=sync_mutation, scalar_overrides=scalar_overrides
    )


@pytest.fixture
def no_session_query(sync_query: type[Any]) -> SyncQueryExecutor:
    return generate_query(query=sync_query, scalar_overrides=scalar_overrides)


@dataclass
class QueryInspector:
    clause_element: Compiled | str | ClauseElement
    dialect: Dialect
    multiparams: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    params: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def statement_str(self) -> str:
        compiled = self.clause_element
        if isinstance(self.clause_element, ClauseElement):
            compiled = self.clause_element.compile(dialect=self.dialect)
        return str(compiled)

    @property
    def statement_formatted(self) -> str:
        return sqlparse.format(
            self.statement_str, reindent_aligned=True, use_space_around_operators=True, keyword_case="upper"
        )


@dataclass
class QueryTracker:
    session: AnySession

    executions: list[QueryInspector] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self._clause_map = {"insert": Insert, "select": Select, "update": Update, "delete": Delete}
        listens_for(self.session.get_bind(), "after_execute")(self._event_listener)

    def _event_listener(
        self,
        conn: Connection | AsyncConnection,
        clauseelement: Compiled | str | ClauseElement,
        multiparams: list[dict[str, Any]],
        params: dict[str, Any],
        execution_options: dict[str, Any],
        result: CursorResult[Any],
    ) -> None:
        self.executions.append(QueryInspector(clauseelement, conn.dialect, multiparams, params))

    def filter(self, statement: FilterableStatement) -> Self:
        return dataclasses.replace(
            self,
            executions=[
                execution
                for execution in self.executions
                if isinstance(execution.clause_element, self._clause_map[statement])
            ],
        )

    @property
    def query_count(self) -> int:
        return len(self.executions)

    def __getitem__(self, index: int) -> QueryInspector:
        return self.executions[index]

    def __iter__(self) -> Iterator[QueryInspector]:
        return iter(self.executions)

    def assert_statements(
        self, count: int, statement_type: FilterableStatement | None = None, snapshot: SnapshotAssertion | None = None
    ) -> None:
        filtered = self.filter(statement_type) if statement_type is not None else self
        assert filtered.query_count == count
        if snapshot is not None:
            for query in filtered:
                assert query.statement_formatted == snapshot
