from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import ColorWithFilteredFruit, FilteredFruitType, FruitTypeWithDescription, OrderedFruitType, strawchemy
from .typing import RawRecordData

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from .fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitTypeWithDescription] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    fruits_paginated: list[FruitTypeWithDescription] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, pagination=True
    )
    filtered_fruits: list[FilteredFruitType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    filtered_fruits_paginated: list[FilteredFruitType] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, pagination=True
    )
    ordered_fruits: list[OrderedFruitType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    ordered_fruits_paginated: list[OrderedFruitType] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, pagination=True
    )
    colors: list[ColorWithFilteredFruit] = strawchemy.field(repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    fruits: list[FruitTypeWithDescription] = strawchemy.field(repository_type=StrawchemySyncRepository)
    fruits_paginated: list[FruitTypeWithDescription] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )
    filtered_fruits: list[FilteredFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    filtered_fruits_paginated: list[FilteredFruitType] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )
    ordered_fruits: list[OrderedFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    ordered_fruits_paginated: list[OrderedFruitType] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )
    colors: list[ColorWithFilteredFruit] = strawchemy.field(repository_type=StrawchemySyncRepository)


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.mark.parametrize("fruits_query", ["fruits", "fruitsPaginated"])
@pytest.mark.snapshot
async def test_load_columns_hook(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ description }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"description": f"The {raw_fruits[0]['name']} is {', '.join(raw_fruits[0]['adjectives'])}"},
        {"description": f"The {raw_fruits[1]['name']} is {', '.join(raw_fruits[1]['adjectives'])}"},
        {"description": f"The {raw_fruits[2]['name']} is {', '.join(raw_fruits[2]['adjectives'])}"},
        {"description": f"The {raw_fruits[3]['name']} is {', '.join(raw_fruits[3]['adjectives'])}"},
        {"description": f"The {raw_fruits[4]['name']} is {', '.join(raw_fruits[4]['adjectives'])}"},
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("fruits_query", ["fruits", "fruitsPaginated"])
async def test_empty_query_hook(fruits_query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ emptyQueryHook }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[fruits_query]) == 5
    assert result.data[fruits_query] == [{"emptyQueryHook": "success"} for _ in range(5)]


@pytest.mark.parametrize("query", ["filteredFruits", "filteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_where(
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == 1
    assert result.data[query] == [{"name": "Apple"}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["orderedFruits", "orderedFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_order_by(
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == 5
    assert result.data[query] == [
        {"name": "Apple"},
        {"name": "Banana"},
        {"name": "Orange"},
        {"name": "Strawberry"},
        {"name": "Watermelon"},
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_on_type(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ colors { fruits { name } } }"))

    assert not result.errors
    assert result.data
    assert len(result.data["colors"]) == 1
    assert result.data["colors"] == [{"fruits": [{"name": "Apple"}]}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
