from __future__ import annotations

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import ColorTypeWithPagination, FruitFilter, FruitTypeWithPaginationAndOrderBy, strawchemy

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemyAsyncRepository
    )
    fruits_aggregations: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemyAsyncRepository
    )
    colors: list[ColorTypeWithPagination] = strawchemy.field(repository_type=StrawchemyAsyncRepository, pagination=True)


@strawberry.type
class SyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemySyncRepository
    )
    fruits_aggregations: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemySyncRepository
    )
    colors: list[ColorTypeWithPagination] = strawchemy.field(repository_type=StrawchemySyncRepository, pagination=True)


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


async def test_pagination(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
            """
            {
                fruits(offset: 1, limit: 1) {
                    name
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["fruits"], list)
    assert result.data["fruits"] == [{"name": "Banana"}]


async def test_nested_pagination(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
            """
            {
                colors(limit: 1) {
                    fruits(limit: 1) {
                        name
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["colors"], list)
    assert len(result.data["colors"]) == 1
    assert isinstance(result.data["colors"][0]["fruits"], list)
    assert len(result.data["colors"][0]["fruits"]) == 1
