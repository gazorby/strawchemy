from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import pytest
import strawberry
from sqlalchemy import Insert, insert, select

from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker


pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Pink"}]


def _schema(strawchemy: Strawchemy) -> Operations:
    repository_type = strawchemy.config.repository_type

    @strawchemy.type(Color, include=["id", "name"])
    class ColorType: ...

    @strawberry.type
    class AsyncQuery:
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
        @strawchemy.field(graphql_type=ColorType)
        def red_color(self, info: strawberry.Info) -> ColorType:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
            return repo.get_one().graphql_type()

        @strawchemy.field(graphql_type=ColorType | None)
        def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
            repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
            return repo.get_one_or_none().graphql_type_or_none()

    return Operations(query=AsyncQuery if issubclass(repository_type, StrawchemyAsyncRepository) else SyncQuery)


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
