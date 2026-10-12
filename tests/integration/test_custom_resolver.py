from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

import pytest
import strawberry
from sqlalchemy import Insert, insert, inspect, select

from strawchemy import Input, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color
from tests.integration.utils import data_argument, to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker


pytestmark = [pytest.mark.integration]

_T = TypeVar("_T")

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Pink"}]


def _schema(strawchemy: Strawchemy) -> Operations:
    repository_type = strawchemy.config.repository_type

    @strawchemy.type(Color, include=["id", "name"])
    class ColorType: ...

    @strawchemy.create_input(Color, include=["name"])
    class ColorCreateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name"])
    class ColorUpdateInput: ...

    @strawberry.type
    class AsyncQuery:
        colors: list[ColorType] = strawchemy.field()

        @strawchemy.field(graphql_type=ColorType)
        async def red_color(self, info: strawberry.Info) -> ColorType:
            repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
            return (await repo.get_one()).graphql_type()

        @strawchemy.field(graphql_type=ColorType | None)
        async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
            repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
            return (await repo.get_one_or_none()).graphql_type_or_none()

    @strawberry.type
    class SyncQuery:
        colors: list[ColorType] = strawchemy.field()

        @strawchemy.field(graphql_type=ColorType)
        def red_color(self, info: strawberry.Info) -> ColorType:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
            return repo.get_one().graphql_type()

        @strawchemy.field(graphql_type=ColorType | None)
        def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
            return repo.get_one_or_none().graphql_type_or_none()

    @strawberry.type
    class AsyncMutation:
        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        async def create_color_restricted(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=_red_colors())
            return (await repo.create(Input(data))).graphql_type()

        @strawchemy.field(graphql_type=list[ColorType], arguments=data_argument(list[ColorUpdateInput]))
        async def update_colors_restricted(
            self, info: strawberry.Info, data: list[ColorUpdateInput]
        ) -> list[ColorType]:
            repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=_red_colors())
            return (await repo.update_by_id(Input(data))).graphql_list()

        @strawchemy.field(graphql_type=ColorType | None, arguments=data_argument(ColorUpdateInput))
        async def update_loaded_color_restricted(
            self, info: strawberry.Info, data: ColorUpdateInput
        ) -> ColorType | None:
            loaded = await cast("AsyncSession", info.context.session).get(Color, 1)
            repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=_red_colors())
            updated = await repo.update_by_id(Input(data))
            return _if_crimson(loaded, updated.graphql_type())

    @strawberry.type
    class SyncMutation:
        @strawchemy.field(graphql_type=ColorType, arguments=data_argument(ColorCreateInput))
        def create_color_restricted(self, info: strawberry.Info, data: ColorCreateInput) -> ColorType:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=_red_colors())
            return repo.create(Input(data)).graphql_type()

        @strawchemy.field(graphql_type=list[ColorType], arguments=data_argument(list[ColorUpdateInput]))
        def update_colors_restricted(self, info: strawberry.Info, data: list[ColorUpdateInput]) -> list[ColorType]:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=_red_colors())
            return repo.update_by_id(Input(data)).graphql_list()

        @strawchemy.field(graphql_type=ColorType | None, arguments=data_argument(ColorUpdateInput))
        def update_loaded_color_restricted(self, info: strawberry.Info, data: ColorUpdateInput) -> ColorType | None:
            loaded = cast("Session", info.context.session).get(Color, 1)
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=_red_colors())
            updated = repo.update_by_id(Input(data))
            return _if_crimson(loaded, updated.graphql_type())

    if issubclass(repository_type, StrawchemyAsyncRepository):
        return Operations(query=AsyncQuery, mutation=AsyncMutation)
    return Operations(query=SyncQuery, mutation=SyncMutation)


def _red_colors() -> Select[Color]:
    return select(Color).where(Color.name == "Red")


# The resolvers load Red before updating it; a session instance left stale by the update would still read Red.
def _if_crimson(color: Color | None, result: _T) -> _T | None:
    return result if color is not None and inspect(color).attrs.name.loaded_value == "Crimson" else None


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS)]


@pytest.mark.snapshot
async def test_get_one(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ redColor { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["redColor"] == {"name": "Red"}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("color", ["unknown", "Pink"])
@pytest.mark.snapshot
async def test_get_one_or_none(color: Literal["unknown", "Pink"], any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(f"""
            {{
                  getColor(color: {to_graphql_representation(color, "input")}) {{
                    name
                }}
            }}
        """)
    )

    assert not result.errors
    assert result.data
    assert result.data["getColor"] == ({"name": "Pink"} if color == "Pink" else None)


@pytest.mark.parametrize(
    ("mutation", "expected", "names_after"),
    [
        pytest.param(
            'createColorRestricted(data: { name: "Blue" })',
            {"name": "Blue"},
            ["Blue", "Pink", "Red", "Yellow"],
            id="create",
        ),
        pytest.param(
            'updateLoadedColorRestricted(data: { id: 1, name: "Crimson" })',
            {"name": "Crimson"},
            ["Crimson", "Pink", "Yellow"],
            id="update-one",
        ),
        pytest.param(
            'updateColorsRestricted(data: [{ id: 1, name: "Crimson" }])',
            [{"name": "Crimson"}],
            ["Crimson", "Pink", "Yellow"],
            id="update-many",
        ),
    ],
)
async def test_mutation_returns_rows_written_outside_filter_statement(
    mutation: str, expected: object, names_after: list[str], any_query: AnyQueryExecutor
) -> None:
    """A repository mutation returns the rows it wrote, even those its filter statement no longer selects."""
    result = await maybe_async(any_query(f"mutation {{ {mutation} {{ name }} }}"))
    assert not result.errors
    assert result.data
    assert next(iter(result.data.values())) == expected

    result = await maybe_async(any_query("{ colors { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(color["name"] for color in result.data["colors"]) == names_after
