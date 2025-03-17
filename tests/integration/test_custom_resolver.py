from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import select
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .models import Color
from .types import ColorType, strawchemy

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from .fixtures import QueryTracker


pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    @strawchemy.field
    async def red_color(self, info: strawberry.Info) -> ColorType:
        repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
        return await repo.get_one()

    @strawchemy.field
    async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        return await repo.get_one_or_none()


@strawberry.type
class SyncQuery:
    @strawchemy.field
    def red_color(self, info: strawberry.Info) -> ColorType:
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
        return repo.get_one()

    @strawchemy.field
    def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        return repo.get_one_or_none()


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


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
