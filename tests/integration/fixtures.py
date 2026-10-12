from __future__ import annotations

import dataclasses
import functools
import os
import platform
import re
from collections.abc import Callable
from copy import copy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from time import sleep
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

import psycopg
import pytest
import sqlparse
from psycopg.sql import SQL, Identifier
from pytest_databases.docker.postgres import _provide_postgres_service
from pytest_lazy_fixtures import lf
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
)
from sqlalchemy.event import listens_for
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.util import immutabledict
from strawberry.scalars import JSON
from strawberry.schema.types.scalar import DEFAULT_SCALAR_REGISTRY
from typing_extensions import Self

from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig, StrawchemySyncRepository
from strawchemy.config.databases import DatabaseFeatures
from strawchemy.constants import GEO_INSTALLED
from strawchemy.schema.scalars import Date, DateTime, Interval, Time
from tests.duplicate_reads import assert_no_duplicate_reads
from tests.integration.models import (
    metadata,
)
from tests.typing import AnyQueryExecutor
from tests.utils import generate_query

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterator
    from pathlib import Path

    from pytest import FixtureRequest
    from pytest_databases._service import DockerService
    from pytest_databases.docker.mysql import MySQLService
    from pytest_databases.docker.postgres import PostgresService
    from pytest_databases.types import XdistIsolationLevel
    from syrupy.assertion import SnapshotAssertion

    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SupportedDialect

__all__ = (
    "ASYNCPG_ENGINE_PARAM",
    "ASYNC_ENGINE_PARAMS",
    "Operations",
    "QueryTracker",
    "SchemaBuilder",
    "SchemaTypes",
    "StatementCounter",
    "any_async_query",
    "any_async_session",
    "any_query",
    "async_engine",
    "async_session",
    "asyncpg_engine",
    "engine",
    "expire_on_commit",
    "psycopg_async_engine",
    "psycopg_engine",
    "seed_db_async",
    "seed_db_sync",
    "session",
)

DATABASE_NAMESPACE_ENV_VAR = "STRAWCHEMY_TEST_DB_NAMESPACE"

_DATABASE_NAMESPACE_PATTERN = re.compile(r"[A-Za-z0-9_]+")

FilterableStatement: TypeAlias = Literal["insert", "update", "select", "delete"]
scalar_overrides: dict[object, Any] = {
    dict[str, Any]: DEFAULT_SCALAR_REGISTRY[JSON],
    timedelta: Interval,
    time: Time,
    date: Date,
    datetime: DateTime,
}
engine_plugins: list[str] = []

if GEO_INSTALLED:
    from strawchemy.schema.scalars.geo import GEO_SCALAR_OVERRIDES

    engine_plugins = ["geoalchemy2"]
    scalar_overrides |= GEO_SCALAR_OVERRIDES

ASYNC_ENGINE_PARAMS = (
    pytest.param(
        "aiosqlite_engine",
        marks=[
            pytest.mark.aiosqlite,
            pytest.mark.integration,
            pytest.mark.xdist_group("sqlite"),
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
    pytest.param(
        "asyncmy_engine",
        marks=[
            pytest.mark.asyncmy,
            pytest.mark.integration,
            pytest.mark.xdist_group("mysql"),
        ],
    ),
)
ASYNCPG_ENGINE_PARAM = pytest.param(
    "asyncpg_engine",
    marks=[
        pytest.mark.asyncpg,
        pytest.mark.integration,
        pytest.mark.xdist_group("postgres"),
    ],
)


def _requested_session(request: FixtureRequest) -> AnySession:
    return request.getfixturevalue("any_session" if "any_session" in request.fixturenames else "any_async_session")


def _query_executor(
    session: Session | AsyncSession,
    request: FixtureRequest,
    sync_query: type[Any],
    async_query: type[Any],
    sync_mutation: type[Any] | None,
    async_mutation: type[Any] | None,
) -> AnyQueryExecutor:
    if isinstance(session, AsyncSession):
        request.getfixturevalue("seed_db_async")
        return generate_query(
            session=session, query=async_query, mutation=async_mutation, scalar_overrides=scalar_overrides
        )
    request.getfixturevalue("seed_db_sync")

    return generate_query(session=session, query=sync_query, mutation=sync_mutation, scalar_overrides=scalar_overrides)


def _namespaced_postgres_service(service: PostgresService, namespace: str) -> PostgresService:
    if not namespace:
        return service
    database = f"{service.database}_{namespace}"
    with psycopg.connect(
        dbname="postgres",
        user=service.user,
        password=service.password,
        host=service.host,
        port=service.port,
        autocommit=True,
    ) as connection:
        if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone() is None:
            connection.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
    return dataclasses.replace(service, database=database)


def _namespaced_mysql_service(service: MySQLService, namespace: str) -> MySQLService:
    if not namespace:
        return service
    database = f"{service.db}_{namespace}"
    command = [
        "mysql",
        f"--user={service.user}",
        f"--password={service.password}",
        "-e",
        f"CREATE DATABASE IF NOT EXISTS {database}",
    ]
    # mysqld restarts once it is done initialising, so an exec can land while the server is down
    # even though the service fixture has just reached it.
    last_output: object = b""
    for attempt in range(15):
        result = service.container.exec_run(command)
        if result.exit_code == 0:
            return dataclasses.replace(service, db=database)
        last_output = result.output
        sleep(1 + attempt * 0.5)
    msg = f"Could not create MySQL database {database!r}: {last_output!r}"
    raise RuntimeError(msg)


@pytest.fixture(autouse=False, scope="session")
def postgis_image() -> str:
    repo = "imresamu/postgis-arm64" if "arm" in platform.processor().lower() else "postgis/postgis"
    return f"{repo}:17-3.5"


@pytest.fixture(scope="session")
def postgis_service(
    docker_service: DockerService,
    xdist_postgres_isolation_level: XdistIsolationLevel,
    postgres_user: str,
    postgres_password: str,
    postgres_host: str,
    postgis_image: str,
) -> Generator[PostgresService]:
    with _provide_postgres_service(
        docker_service,
        image=postgis_image,
        name="postgis-17",
        host=postgres_host,
        user=postgres_user,
        password=postgres_password,
        xdist_postgres_isolate=xdist_postgres_isolation_level,
    ) as service:
        yield service


@pytest.fixture(scope="session")
def database_namespace() -> str:
    """Suffix isolating this checkout's databases from those of any run sharing the containers.

    Raises:
        pytest.UsageError: If the namespace can't be used in a database name.
    """
    namespace = os.environ.get(DATABASE_NAMESPACE_ENV_VAR, "")
    if namespace and not _DATABASE_NAMESPACE_PATTERN.fullmatch(namespace):
        msg = f"{DATABASE_NAMESPACE_ENV_VAR} must only contain letters, digits and underscores, got {namespace!r}"
        raise pytest.UsageError(msg)
    return namespace


@pytest.fixture(scope="session")
def namespaced_postgres_service(postgres_service: PostgresService, database_namespace: str) -> PostgresService:
    return _namespaced_postgres_service(postgres_service, database_namespace)


@pytest.fixture(scope="session")
def namespaced_postgis_service(postgis_service: PostgresService, database_namespace: str) -> PostgresService:
    return _namespaced_postgres_service(postgis_service, database_namespace)


@pytest.fixture(scope="session")
def mysql_service(mysql_84_service: MySQLService, database_namespace: str) -> MySQLService:
    return _namespaced_mysql_service(mysql_84_service, database_namespace)


@pytest.fixture
def postgres_database_service(namespaced_postgres_service: PostgresService) -> PostgresService:
    return namespaced_postgres_service


# Sync engines


@pytest.fixture
def psycopg_engine(postgres_database_service: PostgresService) -> Generator[Engine]:
    """Postgresql instance for end-to-end testing."""
    engine = create_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=postgres_database_service.password,
            host=postgres_database_service.host,
            port=postgres_database_service.port,
            database=postgres_database_service.database,
            query=immutabledict(),
        ),
        poolclass=NullPool,
        plugins=engine_plugins,
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Generator[Engine]:
    db_path = tmp_path / "test.db"
    db_path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


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
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
    ],
)
def engine(request: FixtureRequest) -> Engine:
    return cast("Engine", request.getfixturevalue(request.param))


@pytest.fixture
def expire_on_commit(request: FixtureRequest) -> bool:
    """Whether the session fixtures keep the SQLAlchemy default expiry, set by the marker of the same name."""
    return request.node.get_closest_marker("expire_on_commit") is not None


@pytest.fixture
def session(engine: Engine, expire_on_commit: bool) -> Generator[Session]:
    session = sessionmaker(bind=engine, expire_on_commit=expire_on_commit)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# Async engines


@pytest.fixture
async def asyncmy_engine(mysql_service: MySQLService) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        URL(
            drivername="mysql+asyncmy",
            username=mysql_service.user,
            password=mysql_service.password,
            host=mysql_service.host,
            port=mysql_service.port,
            database=mysql_service.db,
            query=immutabledict(),
        ),
        poolclass=NullPool,
        plugins=engine_plugins,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def aiosqlite_engine(tmp_path: Path) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def asyncpg_engine(postgres_database_service: PostgresService) -> AsyncGenerator[AsyncEngine]:
    """Postgresql instance for end-to-end testing."""
    engine = create_async_engine(
        URL(
            drivername="postgresql+asyncpg",
            username="postgres",
            password=postgres_database_service.password,
            host=postgres_database_service.host,
            port=postgres_database_service.port,
            database=postgres_database_service.database,
            query=immutabledict(),
        ),
        poolclass=NullPool,
        plugins=engine_plugins,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def psycopg_async_engine(postgres_database_service: PostgresService) -> AsyncGenerator[AsyncEngine]:
    """Postgresql instance for end-to-end testing."""
    engine = create_async_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password=postgres_database_service.password,
            host=postgres_database_service.host,
            port=postgres_database_service.port,
            database=postgres_database_service.database,
            query=immutabledict(),
        ),
        poolclass=NullPool,
        plugins=engine_plugins,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(name="async_engine", params=ASYNC_ENGINE_PARAMS)
def async_engine(request: FixtureRequest) -> AsyncEngine:
    return cast("AsyncEngine", request.getfixturevalue(request.param))


@pytest.fixture
async def async_session(async_engine: AsyncEngine, expire_on_commit: bool) -> AsyncGenerator[AsyncSession]:
    session = async_sessionmaker(bind=async_engine, expire_on_commit=expire_on_commit)()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


# DB Seeding


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return []


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
def dialect(request: FixtureRequest) -> SupportedDialect:
    return cast("SupportedDialect", _requested_session(request).get_bind().dialect.name)


@pytest.fixture
def db_features(dialect: SupportedDialect) -> DatabaseFeatures:
    return DatabaseFeatures.new(dialect)


@dataclass(frozen=True)
class Operations:
    query: type[Any]
    mutation: type[Any] | None = None


SchemaBuilder: TypeAlias = Callable[[Strawchemy], Operations]


@functools.cache
def _build_schema_types(dialect: SupportedDialect, builder: SchemaBuilder) -> SchemaTypes:
    async_mapper = Strawchemy(StrawchemyConfig(dialect, repository_type=StrawchemyAsyncRepository))
    sync_mapper = Strawchemy(StrawchemyConfig(dialect, repository_type=StrawchemySyncRepository))
    return SchemaTypes(
        async_mapper=async_mapper,
        sync_mapper=sync_mapper,
        async_operations=builder(async_mapper),
        sync_operations=builder(sync_mapper),
    )


@dataclass(frozen=True)
class SchemaTypes:
    async_mapper: Strawchemy
    sync_mapper: Strawchemy
    async_operations: Operations
    sync_operations: Operations

    @classmethod
    def build(cls, dialect: SupportedDialect, builder: SchemaBuilder) -> Self:
        return cast("Self", _build_schema_types(dialect, builder))


@pytest.fixture
def schema(request: FixtureRequest) -> SchemaTypes:
    pytest.fail(f"{request.module.__name__} must override the schema fixture")


@pytest.fixture
def mapper(schema: SchemaTypes, request: FixtureRequest) -> Strawchemy:
    if isinstance(_requested_session(request), AsyncSession):
        return schema.async_mapper
    return schema.sync_mapper


@pytest.fixture
def config(mapper: Strawchemy) -> Generator[StrawchemyConfig]:
    original_config = copy(mapper.config)
    yield mapper.config
    for field in dataclasses.fields(original_config):
        setattr(mapper.config, field.name, getattr(original_config, field.name))


@pytest.fixture
def async_query(schema: SchemaTypes) -> type[Any]:
    return schema.async_operations.query


@pytest.fixture
def sync_query(schema: SchemaTypes) -> type[Any]:
    return schema.sync_operations.query


@pytest.fixture
def async_mutation(schema: SchemaTypes) -> type[Any] | None:
    return schema.async_operations.mutation


@pytest.fixture
def sync_mutation(schema: SchemaTypes) -> type[Any] | None:
    return schema.sync_operations.mutation


@pytest.fixture(params=[lf("async_session"), lf("session")], ids=["async", "sync"])
def any_session(request: FixtureRequest) -> AnySession:
    return request.param


@pytest.fixture(params=[lf("async_session")], ids=["async"])
def any_async_session(request: FixtureRequest) -> AsyncSession:
    return request.param


@pytest.fixture(params=[None], ids=["tracked"])
def query_tracker(request: FixtureRequest) -> QueryTracker:
    return QueryTracker(_requested_session(request))


@pytest.fixture(params=[None], ids=["session"])
def any_query(
    any_session: Session | AsyncSession,
    sync_query: type[Any],
    async_query: type[Any],
    async_mutation: type[Any] | None,
    sync_mutation: type[Any] | None,
    request: FixtureRequest,
) -> AnyQueryExecutor:
    return _query_executor(any_session, request, sync_query, async_query, sync_mutation, async_mutation)


@pytest.fixture(params=[None], ids=["session"])
def any_async_query(
    any_async_session: AsyncSession,
    sync_query: type[Any],
    async_query: type[Any],
    async_mutation: type[Any] | None,
    sync_mutation: type[Any] | None,
    request: FixtureRequest,
) -> AnyQueryExecutor:
    return _query_executor(any_async_session, request, sync_query, async_query, sync_mutation, async_mutation)


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
            column_keys = list(self.params) or list(self.multiparams[0] if self.multiparams else []) or None
            compiled = self.clause_element.compile(dialect=self.dialect, column_keys=column_keys)
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
        if isinstance(clauseelement, Select):
            assert_no_duplicate_reads(clauseelement, conn.dialect)
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
        return len(
            [
                execution
                for execution in self.executions
                if isinstance(execution.clause_element, tuple(self._clause_map.values()))
            ]
        )

    def __getitem__(self, index: int) -> QueryInspector:
        return self.executions[index]

    def __iter__(self) -> Iterator[QueryInspector]:
        return iter(self.executions)

    def assert_statements(
        self,
        count: int,
        statement_type: FilterableStatement | None = None,
        snapshot: SnapshotAssertion | None = None,
    ) -> None:
        filtered = self.filter(statement_type) if statement_type is not None else self
        assert filtered.query_count == count
        if snapshot is None:
            return
        for query in filtered:
            assert query.statement_formatted == snapshot


@dataclass
class StatementCounter:
    """Count the ORM statements executed on an async session."""

    session: AsyncSession
    count: int = 0

    def __post_init__(self) -> None:
        listens_for(self.session.sync_session, "do_orm_execute")(self._on_execute)

    def _on_execute(self, _: object) -> None:
        self.count += 1
