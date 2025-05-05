from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import (
    ColorTypeHooks,
    ColorWithFilteredFruit,
    FilteredFruitType,
    FruitTypeHooks,
    OrderedFruitType,
    strawchemy,
)
from .typing import RawRecordData

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from .fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitTypeHooks] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    fruits_paginated: list[FruitTypeHooks] = strawchemy.field(
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
    colors_paginated: list[ColorWithFilteredFruit] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, pagination=True
    )
    colors_hooks: list[ColorTypeHooks] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    colors_hooks_paginated: list[ColorTypeHooks] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, pagination=True
    )


@strawberry.type
class SyncQuery:
    fruits: list[FruitTypeHooks] = strawchemy.field(repository_type=StrawchemySyncRepository)
    fruits_paginated: list[FruitTypeHooks] = strawchemy.field(repository_type=StrawchemySyncRepository, pagination=True)
    filtered_fruits: list[FilteredFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    filtered_fruits_paginated: list[FilteredFruitType] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )
    ordered_fruits: list[OrderedFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    ordered_fruits_paginated: list[OrderedFruitType] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )
    colors: list[ColorWithFilteredFruit] = strawchemy.field(repository_type=StrawchemySyncRepository)
    colors_paginated: list[ColorWithFilteredFruit] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )

    colors_hooks: list[ColorTypeHooks] = strawchemy.field(repository_type=StrawchemySyncRepository)
    colors_hooks_paginated: list[ColorTypeHooks] = strawchemy.field(
        repository_type=StrawchemySyncRepository, pagination=True
    )


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
        {"description": f"The {fruit['name']} color id is {fruit['color_id']}"} for fruit in raw_fruits
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("fruits_query", ["fruits", "fruitsPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_with_columns(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ prettyColor }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"prettyColor": f"Color is {next(color['name'] for color in raw_colors if color['id'] == fruit['color_id'])}"}
        for fruit in raw_fruits
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruits", "fruitsPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_no_columns(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ prettyFarms }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [{"prettyFarms": f"Farms are: {fruit['name']} farm"} for fruit in raw_fruits]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colors", "colorsPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_nested(
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ farms }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[query] == [
        {
            "farms": f"Farms are: {', '.join(f'{fruit["name"]} farm' for fruit in raw_fruits if fruit['color_id'] == color['id'])}"
        }
        for color in raw_colors
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsHooks", "colorsHooksPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_on_nested_field(
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ id fruits {{ prettyColor }} }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[query] == [
        {
            "id": color["id"],
            "fruits": [
                {"prettyColor": f"Color is {color['name']}"}
                for _ in range(len([fruit for fruit in raw_fruits if fruit["color_id"] == color["id"]]))
            ],
        }
        for color in raw_colors
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruits", "fruitsPaginated"])
async def test_empty_query_hook(fruits_query: str, any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ emptyQueryHook }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[fruits_query]) == len(raw_fruits)
    assert result.data[fruits_query] == [{"emptyQueryHook": "success"} for _ in range(len(raw_fruits))]


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
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == len(raw_fruits)
    assert result.data[query] == sorted(
        [{"name": fruit["name"]} for fruit in raw_fruits], key=lambda fruit: fruit["name"]
    )

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
