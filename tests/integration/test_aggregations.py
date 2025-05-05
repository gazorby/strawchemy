from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.types import DefaultOffsetPagination

import strawberry
from tests.integration.models import Fruit
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import ColorType, FruitAggregationType, strawchemy
from .typing import RawRecordData
from .utils import compute_aggregation, from_graphql_representation, python_type

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@strawberry.type
class AsyncQuery:
    color: ColorType = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    fruit_aggregations: FruitAggregationType = strawchemy.field(
        root_aggregations=True, repository_type=StrawchemyAsyncRepository
    )
    fruit_aggregations_paginated: FruitAggregationType = strawchemy.field(
        root_aggregations=True, pagination=DefaultOffsetPagination(limit=2), repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncQuery:
    color: ColorType = strawchemy.field(repository_type=StrawchemySyncRepository)
    fruit_aggregations: FruitAggregationType = strawchemy.field(
        root_aggregations=True, repository_type=StrawchemySyncRepository
    )
    fruit_aggregations_paginated: FruitAggregationType = strawchemy.field(
        root_aggregations=True, pagination=DefaultOffsetPagination(limit=2), repository_type=StrawchemySyncRepository
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.mark.snapshot
async def test_count_aggregation(
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the count aggregation function."""
    query = f"""
        {{
            color(id: "{raw_colors[0]["id"]}") {{
                fruitsAggregate {{
                    count
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["color"]["fruitsAggregate"]["count"] == len(
        [fruit for fruit in raw_fruits if fruit["color_id"] == raw_colors[0]["id"]]
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("rarity", "rarity"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the sum aggregation function for a specific field."""
    query = f"""
        {{
            color(id: "{raw_colors[0]["id"]}") {{
                fruitsAggregate {{
                    sum {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    # Calculate expected value
    expected_sum = sum(fruit[raw_field_name] for fruit in raw_fruits if fruit["color_id"] == raw_colors[0]["id"])

    # Verify result
    actual_sum = result.data["color"]["fruitsAggregate"]["sum"][field_name]

    if field_name == "rarity":
        assert str(actual_sum) == str(expected_sum)
    else:
        assert pytest.approx(actual_sum) == expected_sum

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("rarity", "rarity"),
        ("name", "name"),
        ("createdAt", "created_at"),
        ("bestTimeToPick", "best_time_to_pick"),
    ],
)
@pytest.mark.snapshot
async def test_min_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the min aggregation function for a specific field."""
    query = f"""
        {{
            color(id: "{raw_colors[0]["id"]}") {{
                fruitsAggregate {{
                    min {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    # Verify result
    actual_min = from_graphql_representation(
        result.data["color"]["fruitsAggregate"]["min"][field_name], python_type(Fruit, raw_field_name)
    )
    assert actual_min is not None

    # For fields where we can calculate expected values, verify them
    expected_min = min(fruit[raw_field_name] for fruit in raw_fruits if fruit["color_id"] == raw_colors[0]["id"])

    assert actual_min == expected_min

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("rarity", "rarity"),
        ("name", "name"),
        ("createdAt", "created_at"),
        ("bestTimeToPick", "best_time_to_pick"),
    ],
)
@pytest.mark.snapshot
async def test_max_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the max aggregation function for a specific field."""
    query = f"""
        {{
            color(id: "{raw_colors[0]["id"]}") {{
                fruitsAggregate {{
                    max {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    # Verify result
    actual_max = from_graphql_representation(
        result.data["color"]["fruitsAggregate"]["max"][field_name], python_type(Fruit, raw_field_name)
    )
    assert actual_max is not None

    # For fields where we can calculate expected values, verify them
    expected_max = max(fruit[raw_field_name] for fruit in raw_fruits if fruit["color_id"] == raw_colors[0]["id"])

    assert actual_max == expected_max

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "agg_type",
    ["avg", "stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
)
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("rarity", "rarity"),
    ],
)
@pytest.mark.snapshot
async def test_statistical_aggregation(
    agg_type: Literal["avg", "stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    query = f"""
        {{
            color(id: "{raw_colors[0]["id"]}") {{
                fruitsAggregate {{
                    {agg_type} {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    # Verify result is a number or null
    actual_value = from_graphql_representation(
        result.data["color"]["fruitsAggregate"][agg_type][field_name], python_type(Fruit, raw_field_name)
    )

    expected_value = compute_aggregation(
        agg_type, [fruit[raw_field_name] for fruit in raw_fruits if fruit["color_id"] == raw_colors[0]["id"]]
    )

    assert pytest.approx(actual_value) == expected_value

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "pagination",
    [pytest.param(None, id="no-pagination"), pytest.param(DefaultOffsetPagination(limit=2), id="pagination")],
)
@pytest.mark.parametrize(
    "agg_type",
    ["avg", "stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
)
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("rarity", "rarity"),
    ],
)
@pytest.mark.snapshot
async def test_root_aggregation(
    agg_type: Literal["avg", "stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    pagination: None | DefaultOffsetPagination,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    query_name = "fruitAggregations" if pagination is None else "fruitAggregationsPaginated"
    query = f"""
        {{
            {query_name} {{
                aggregations {{
                    {agg_type} {{
                        {field_name}
                    }}
                }}
                nodes {{
                    id
                    {field_name}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    # Verify result is a number or null
    actual_value = from_graphql_representation(
        result.data[query_name]["aggregations"][agg_type][field_name], python_type(Fruit, raw_field_name)
    )
    if pagination is None:
        expected_value = compute_aggregation(agg_type, [record[raw_field_name] for record in raw_fruits])
    else:
        expected_value = compute_aggregation(
            agg_type, [record[raw_field_name] for record in raw_fruits[: pagination.limit]]
        )

    assert pytest.approx(actual_value) == expected_value

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
