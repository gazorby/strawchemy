from __future__ import annotations

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import (
    ColorTypeWithPagination,
    FruitAggregationType,
    FruitFilter,
    FruitTypeWithPaginationAndOrderBy,
    strawchemy,
)

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemyAsyncRepository
    )
    fruits_aggregations: FruitAggregationType = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemyAsyncRepository, root_aggregations=True
    )
    colors: list[ColorTypeWithPagination] = strawchemy.field(repository_type=StrawchemyAsyncRepository, pagination=True)


@strawberry.type
class SyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemySyncRepository
    )
    fruits_aggregations: FruitAggregationType = strawchemy.field(
        filter_input=FruitFilter, pagination=True, repository_type=StrawchemySyncRepository, root_aggregations=True
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
    assert len(result.data["fruits"]) == 1
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


async def test_pagination_on_aggregation_query(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
            """
            {
                fruitsAggregations(offset: 1, limit: 1) {
                    nodes {
                        name
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["fruitsAggregations"]["nodes"], list)
    assert len(result.data["fruitsAggregations"]["nodes"]) == 1
    assert result.data["fruitsAggregations"]["nodes"] == [{"name": "Banana"}]
