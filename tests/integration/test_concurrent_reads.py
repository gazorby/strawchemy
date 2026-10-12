"""Integration tests for concurrent root reads."""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, NoReturn

import pytest
import strawberry
from sqlalchemy import Insert, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strawchemy import Input, StrawchemyAsyncRepository, StrawchemyExecutionContext
from tests.integration.fixtures import Operations, SchemaTypes, StatementCounter, scalar_overrides
from tests.integration.models import Color, Fruit, User
from tests.utils import StrawberryContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.orm import Session
    from strawberry.schema._graphql_core import GraphQLExecutionContext
    from strawberry.types import ExecutionResult

    from strawchemy import Strawchemy
    from strawchemy.config.base import StrawchemyConfig
    from strawchemy.typing import SupportedDialect
    from tests.integration.typing import RawRecordData

pytestmark = [pytest.mark.integration]

_COLORS: RawRecordData = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Green"}]
# The first color owns two fruits and another color one, so relation reads and updates discriminate.
_FRUITS: RawRecordData = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
]
_USERS: RawRecordData = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


@dataclass(frozen=True)
class _Types:
    color: type[Any]
    fruit: type[Any]
    user: type[Any]
    color_create_input: type[Any]
    query: type[Any]
    mutation: type[Any]


@functools.cache
def _types(strawchemy: Strawchemy) -> _Types:
    @strawchemy.type(Color, include=["id", "name", "fruits"], override=True)
    class ColorType: ...

    @strawchemy.type(Fruit, include=["id", "name", "color"], override=True)
    class FruitType: ...

    @strawchemy.type(User, include=["name"])
    class UserType: ...

    @strawchemy.create_input(Color, include=["name"])
    class ColorCreateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name"])
    class ColorUpdateInput: ...

    @strawchemy.pk_update_input(Fruit, include=["id", "name"])
    class FruitUpdateInput: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field()
        colors: list[ColorType] = strawchemy.field()
        fruits: list[FruitType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)
        update_colors: list[ColorType] = strawchemy.update_by_ids(ColorUpdateInput)
        update_fruits: list[FruitType] = strawchemy.update_by_ids(FruitUpdateInput)

    return _Types(ColorType, FruitType, UserType, ColorCreateInput, Query, Mutation)


def _schema(strawchemy: Strawchemy) -> Operations:
    types = _types(strawchemy)
    return Operations(query=types.query, mutation=types.mutation)


class _RecordingSession(AsyncSession):
    recorder: ReadSessions
    key: str | int

    async def close(self) -> None:
        await super().close()
        self.recorder.closed.append(self.key)


class ReadSessions:
    """Read session getter recording which root field opened and closed each session."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Wrap the engine in a recording sessionmaker."""
        self._sessionmaker = async_sessionmaker(bind=engine, class_=_RecordingSession)
        self.opened: list[str | int] = []
        self.closed: list[str | int] = []
        self.peak = 0
        self._peak_reached: dict[int, asyncio.Event] = {}

    def __call__(self, info: strawberry.Info[Any, Any]) -> AsyncSession:
        """Open a recording session attributed to the field being resolved."""
        session = self._sessionmaker()
        session.recorder = self
        session.key = info.path.key
        self.opened.append(session.key)
        self.peak = max(self.peak, len(self.opened) - len(self.closed))
        for peak, reached in self._peak_reached.items():
            if peak <= self.peak:
                reached.set()
        return session

    async def wait_for_peak(self, peak: int) -> None:
        """Wait until `peak` read sessions are open at once, failing after a timeout instead of hanging."""
        reached = self._peak_reached.setdefault(peak, asyncio.Event())
        if self.peak >= peak:
            reached.set()
        await asyncio.wait_for(reached.wait(), timeout=5)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(User).values(_USERS)]


@pytest.fixture
def read_sessions(async_engine: AsyncEngine) -> ReadSessions:
    """Provide the recording read session getter."""
    return ReadSessions(async_engine)


@pytest.fixture
def request_statements(any_async_session: AsyncSession) -> StatementCounter:
    """Count the statements executed on the request session."""
    return StatementCounter(any_async_session)


@pytest.fixture
def run(
    any_async_session: AsyncSession,
    config: StrawchemyConfig,
    read_sessions: ReadSessions,
    async_query: type[Any],
    async_mutation: type[Any] | None,
    request: pytest.FixtureRequest,
) -> Callable[..., Callable[[str], Awaitable[ExecutionResult]]]:
    """Provide a factory building a schema with concurrent reads enabled and executing documents."""
    config.read_session_getter = read_sessions
    request.getfixturevalue("seed_db_async")

    def factory(
        query_type: type[Any] | None = None,
        mutation_type: type[Any] | None = None,
        execution_context_class: type[GraphQLExecutionContext] | None = None,
    ) -> Callable[[str], Awaitable[ExecutionResult]]:
        schema = strawberry.Schema(
            query=query_type or async_query,
            mutation=mutation_type or async_mutation,
            scalar_overrides=scalar_overrides,
            execution_context_class=execution_context_class,
        )
        context = StrawberryContext(any_async_session)

        async def execute(query: str) -> ExecutionResult:
            return await schema.execute(query, context_value=context)

        return execute

    return factory


async def test_query_roots_use_read_sessions(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    read_sessions: ReadSessions,
    request_statements: StatementCounter,
) -> None:
    """Test that each strawchemy root of a query runs on its own read session."""
    result = await run()("{ users { name } colors { name } fruits { name } }")

    assert not result.errors
    assert sorted(read_sessions.opened) == ["colors", "fruits", "users"]
    assert sorted(read_sessions.opened) == sorted(read_sessions.closed)
    assert request_statements.count == 0
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in _USERS]
    assert result.data["colors"] == [{"name": color["name"]} for color in _COLORS]
    assert result.data["fruits"] == [{"name": fruit["name"]} for fruit in _FRUITS]


async def test_query_roots_without_getter_share_request_session(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    config: StrawchemyConfig,
    read_sessions: ReadSessions,
    request_statements: StatementCounter,
) -> None:
    """Test that without a read getter, roots run on the request session as before."""
    config.read_session_getter = None

    result = await run()("{ users { name } colors { name } fruits { name } }")

    assert not result.errors
    assert read_sessions.opened == []
    assert request_statements.count == 3
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in _USERS]
    assert result.data["colors"] == [{"name": color["name"]} for color in _COLORS]
    assert result.data["fruits"] == [{"name": fruit["name"]} for fruit in _FRUITS]


async def test_pending_add_keeps_reads_on_request_session(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    any_async_session: AsyncSession,
    read_sessions: ReadSessions,
) -> None:
    """Test that an unflushed add on the request session keeps reads on it."""
    any_async_session.add(Color(name="Pending"))

    result = await run()("{ colors { name } }")

    assert not result.errors
    assert read_sessions.opened == []
    assert result.data
    assert "Pending" in [color["name"] for color in result.data["colors"]]


async def test_explicit_session_is_used_as_given(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    async_engine: AsyncEngine,
    mapper: Strawchemy,
    read_sessions: ReadSessions,
    request_statements: StatementCounter,
) -> None:
    """Test that a repository built with an explicit session never opens a read session."""
    color_type = _types(mapper).color
    explicit_session = async_sessionmaker(bind=async_engine)()
    explicit_statements = StatementCounter(explicit_session)

    async def resolve_colors(info: strawberry.Info) -> list[Any]:
        repository = StrawchemyAsyncRepository(color_type, info, session=explicit_session)
        return (await repository.list()).graphql_list()

    resolve_colors.__annotations__["return"] = list[color_type]

    query_type = strawberry.type(type("Query", (), {"explicit_colors": strawberry.field(resolver=resolve_colors)}))

    try:
        result = await run(query_type=query_type)("{ explicitColors { name } }")
    finally:
        await explicit_session.close()

    assert not result.errors
    assert read_sessions.opened == []
    assert request_statements.count == 0
    assert explicit_statements.count == 1
    assert result.data
    assert sorted(color["name"] for color in result.data["explicitColors"]) == sorted(
        color["name"] for color in _COLORS
    )


def _session_scope_types(mapper: Strawchemy) -> tuple[type[Any], type[Any]]:
    async def color_count(info: strawberry.Info) -> int:
        async with mapper.read_session(info) as session:
            return (await session.execute(select(func.count(Color.id)))).scalar_one()

    async def touch_color(info: strawberry.Info) -> int:
        async with mapper.write_session(info) as session:
            await session.execute(update(Color).where(Color.id == 1).values(name="Touched"))
        return 1

    query_type = strawberry.type(type("Query", (), {"color_count": strawberry.field(resolver=color_count)}))
    mutation_type = strawberry.type(type("Mutation", (), {"touch_color": strawberry.field(resolver=touch_color)}))
    return query_type, mutation_type


async def test_read_session_in_custom_resolver(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    read_sessions: ReadSessions,
) -> None:
    """Test that a custom resolver reading through read_session gets a read session."""
    query_type, mutation_type = _session_scope_types(mapper)

    result = await run(query_type=query_type, mutation_type=mutation_type)("{ colorCount }")

    assert not result.errors
    assert result.data == {"colorCount": len(_COLORS)}
    assert read_sessions.opened == ["colorCount"]


async def test_write_session_moves_later_reads_to_request_session(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    read_sessions: ReadSessions,
) -> None:
    """Test that a read after write_session runs on the request session."""
    query_type, mutation_type = _session_scope_types(mapper)
    execute = run(query_type=query_type, mutation_type=mutation_type)

    written = await execute("mutation { touchColor }")
    result = await execute("{ colorCount }")

    assert not written.errors
    assert not result.errors
    assert result.data == {"colorCount": len(_COLORS)}
    assert read_sessions.opened == []


async def test_commit_reenables_read_sessions(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    any_async_session: AsyncSession,
    read_sessions: ReadSessions,
) -> None:
    """Test that committing the request session after a write lets later reads use read sessions."""
    query_type, mutation_type = _session_scope_types(mapper)
    execute = run(query_type=query_type, mutation_type=mutation_type)

    written = await execute("mutation { touchColor }")
    await any_async_session.commit()
    result = await execute("{ colorCount }")

    assert not written.errors
    assert not result.errors
    assert read_sessions.opened == ["colorCount"]


def test_sync_read_session_yields_request_session(any_session: Session, mapper: Strawchemy) -> None:
    """Test that the sync read_session yields the request session."""
    with mapper.read_session(SimpleNamespace(context={"session": any_session})) as yielded:  # ty: ignore[invalid-argument-type]  # minimal info stand-in
        assert yielded is any_session


def _concurrent_mutation_type(mapper: Strawchemy, read_sessions: ReadSessions) -> type[Any]:
    types = _types(mapper)

    async def gated_colors(info: strawberry.Info) -> list[Any]:
        async with mapper.read_session(info) as session:
            await read_sessions.wait_for_peak(2)
            return (await StrawchemyAsyncRepository(types.color, info, session=session).list()).graphql_list()

    async def plain_count(info: strawberry.Info) -> int:
        async with mapper.read_session(info) as session:
            return (await session.execute(select(func.count(Color.id)))).scalar_one()

    async def broken() -> NoReturn:
        msg = "broken read"
        raise ValueError(msg)

    async def broken_required() -> NoReturn:
        msg = "broken read"
        raise ValueError(msg)

    async def create_explicit_color(info: strawberry.Info, data: object) -> object:
        repository = StrawchemyAsyncRepository(types.color, info, session=info.context.session)
        return (await repository.create(Input(data))).graphql_type()

    gated_colors.__annotations__["return"] = list[types.color]
    create_explicit_color.__annotations__.update({"data": types.color_create_input, "return": types.color})
    broken.__annotations__["return"] = types.color | None
    broken_required.__annotations__["return"] = types.color

    namespace = {
        "__annotations__": {"colors": list[types.color], "fruits": list[types.fruit]},
        "colors": mapper.field(repository_type=StrawchemyAsyncRepository),
        "fruits": mapper.field(repository_type=StrawchemyAsyncRepository),
        "gated_colors": mapper.field(gated_colors, read_only=True),
        "plain_count": mapper.field(plain_count),
        "broken": mapper.field(broken, read_only=True),
        "broken_required": mapper.field(broken_required, read_only=True),
        "create_explicit_color": strawberry.mutation(resolver=create_explicit_color),
    }
    return strawberry.type(type("Mutation", (types.mutation,), namespace))


@pytest.fixture
def run_mutation(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    read_sessions: ReadSessions,
) -> Callable[[str], Awaitable[ExecutionResult]]:
    """Provide an executor for the mixed read, write and custom resolver mutation."""
    return run(
        mutation_type=_concurrent_mutation_type(mapper, read_sessions),
        execution_context_class=StrawchemyExecutionContext,
    )


async def _color_name(session: AsyncSession, color_id: int) -> str:
    return (await session.execute(select(Color.name).where(Color.id == color_id))).scalar_one()


async def test_mutation_reads_before_write_run_concurrently(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    read_sessions: ReadSessions,
) -> None:
    """Test that reads before the first write gather, and reads after it see the write on the request session."""
    result = await run_mutation(f"""mutation {{
        gatedColors {{ name }}
        colors {{ name fruits {{ name }} }}
        updateColors(data: [{{ id: {_COLORS[0]["id"]}, name: "Updated" }}]) {{ id }}
        fruits {{ color {{ name }} }}
    }}""")

    assert not result.errors
    assert sorted(read_sessions.opened) == ["colors", "gatedColors"]
    assert sorted(read_sessions.closed) == ["colors", "gatedColors"]
    assert read_sessions.peak == 2
    assert result.data
    assert list(result.data) == ["gatedColors", "colors", "updateColors", "fruits"]
    assert sorted(color["name"] for color in result.data["gatedColors"]) == sorted(c["name"] for c in _COLORS)
    first_color = next(color for color in result.data["colors"] if color["name"] == _COLORS[0]["name"])
    assert sorted(fruit["name"] for fruit in first_color["fruits"]) == sorted(
        fruit["name"] for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"]
    )
    assert "Updated" in {fruit["color"]["name"] for fruit in result.data["fruits"]}


async def test_reads_after_write_stay_on_request_session(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    read_sessions: ReadSessions,
) -> None:
    """Test that `{write read read write}` runs every root on the request session in order."""
    result = await run_mutation(f"""mutation {{
        updateFruits(data: [{{ id: {_FRUITS[0]["id"]}, name: "Updated fruit" }}]) {{ id }}
        fruits {{ name }}
        colors {{ name }}
        updateColor(data: {{ id: {_COLORS[0]["id"]}, name: "Updated" }}) {{ name }}
    }}""")

    assert not result.errors
    assert read_sessions.opened == []
    assert result.data
    assert list(result.data) == ["updateFruits", "fruits", "colors", "updateColor"]
    assert "Updated fruit" in {fruit["name"] for fruit in result.data["fruits"]}
    assert "Updated" not in {color["name"] for color in result.data["colors"]}
    assert result.data["updateColor"] == {"name": "Updated"}


async def test_write_through_explicit_request_session_keeps_later_reads_on_it(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    read_sessions: ReadSessions,
) -> None:
    """Test that a write through a repository given the request session keeps later reads on that session."""
    result = await run_mutation("""mutation {
        createExplicitColor(data: { name: "Explicit" }) { name }
        colors { name }
        fruits { name }
    }""")

    assert not result.errors
    assert read_sessions.opened == []
    assert result.data
    assert result.data["createExplicitColor"] == {"name": "Explicit"}
    assert "Explicit" in {color["name"] for color in result.data["colors"]}


async def test_mutation_without_execution_context_is_serial(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    read_sessions: ReadSessions,
) -> None:
    """Test that without StrawchemyExecutionContext, mutation roots run serially and correctly."""
    execute = run(mutation_type=_concurrent_mutation_type(mapper, read_sessions))

    result = await execute(f"""mutation {{
        colors {{ name }}
        updateColors(data: [{{ id: {_COLORS[0]["id"]}, name: "Updated" }}]) {{ id }}
        fruits {{ color {{ name }} }}
    }}""")

    assert not result.errors
    assert read_sessions.opened == ["colors"]
    assert read_sessions.peak <= 1
    assert result.data
    assert list(result.data) == ["colors", "updateColors", "fruits"]
    assert sorted(color["name"] for color in result.data["colors"]) == sorted(c["name"] for c in _COLORS)
    assert "Updated" in {fruit["color"]["name"] for fruit in result.data["fruits"]}


async def test_unmarked_resolver_splits_group(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    read_sessions: ReadSessions,
) -> None:
    """Test that an unmarked custom resolver between reads acts as a barrier."""
    result = await run_mutation("mutation { colors { name } plainCount fruits { name } }")

    assert not result.errors
    assert read_sessions.opened == ["colors", "plainCount", "fruits"]
    assert read_sessions.peak == 1
    assert result.data
    assert list(result.data) == ["colors", "plainCount", "fruits"]
    assert result.data["plainCount"] == len(_COLORS)


async def test_aliased_reads_join_group(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    read_sessions: ReadSessions,
) -> None:
    """Test that one root selected under two aliases joins the same concurrent group."""
    result = await run_mutation("mutation { gatedColors { name } a: colors { id } b: colors { name } }")

    assert not result.errors
    assert sorted(read_sessions.opened) == ["a", "b", "gatedColors"]
    assert read_sessions.peak >= 2
    assert result.data
    assert list(result.data) == ["gatedColors", "a", "b"]
    assert len(result.data["a"]) == len(_COLORS)
    assert sorted(color["name"] for color in result.data["b"]) == sorted(c["name"] for c in _COLORS)


async def test_nullable_read_error_continues(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    any_async_session: AsyncSession,
) -> None:
    """Test that a failing nullable read yields null and later mutations still run."""
    result = await run_mutation(f"""mutation {{
        broken {{ name }}
        colors {{ name }}
        updateColor(data: {{ id: {_COLORS[0]["id"]}, name: "Updated" }}) {{ name }}
    }}""")

    assert result.errors
    assert [error.path for error in result.errors] == [["broken"]]
    assert result.data
    assert result.data["broken"] is None
    assert result.data["updateColor"] == {"name": "Updated"}
    assert await _color_name(any_async_session, _COLORS[0]["id"]) == "Updated"


async def test_non_null_read_error_stops_later_groups(
    run_mutation: Callable[[str], Awaitable[ExecutionResult]],
    any_async_session: AsyncSession,
    read_sessions: ReadSessions,
) -> None:
    """Test that a failing non-null read nulls data and skips later mutations."""
    result = await run_mutation(f"""mutation {{
        brokenRequired {{ name }}
        colors {{ name }}
        updateColor(data: {{ id: {_COLORS[0]["id"]}, name: "Updated" }}) {{ name }}
    }}""")

    assert result.errors
    assert result.data is None
    assert await _color_name(any_async_session, _COLORS[0]["id"]) == _COLORS[0]["name"]
    assert sorted(read_sessions.opened) == sorted(read_sessions.closed)


async def test_read_getter_error_is_field_error(
    run: Callable[..., Callable[[str], Awaitable[ExecutionResult]]],
    mapper: Strawchemy,
    config: StrawchemyConfig,
    read_sessions: ReadSessions,
) -> None:
    """Test that a read getter raising gives a field error while other fields resolve."""
    types = _types(mapper)
    namespace = {
        "__annotations__": {"colors": list[types.color] | None, "users": list[types.user]},
        "colors": mapper.field(repository_type=StrawchemyAsyncRepository),
        "users": mapper.field(repository_type=StrawchemyAsyncRepository),
    }
    execute = run(query_type=strawberry.type(type("Query", (), namespace)))

    def failing_getter(info: strawberry.Info[Any, Any]) -> AsyncSession:
        if info.path.key == "colors":
            msg = "no read session"
            raise RuntimeError(msg)
        return read_sessions(info)

    config.read_session_getter = failing_getter

    result = await execute("{ colors { name } users { name } }")

    assert result.errors
    assert [error.path for error in result.errors] == [["colors"]]
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in _USERS]
