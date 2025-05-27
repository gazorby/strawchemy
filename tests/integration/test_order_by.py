from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData
from .utils import compute_aggregation

if TYPE_CHECKING:
    from decimal import Decimal

    from strawchemy.config.databases import DatabaseFeatures

pytestmark = [pytest.mark.integration]


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by(
    order_by: Literal["ASC", "DESC"],
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(f"{{ fruits(orderBy: {{ sweetness: {order_by} }}) {{ id sweetness }} }}"))
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [{"id": row["id"], "sweetness": row["sweetness"]} for row in raw_fruits]
    expected_sort = sorted(expected_sort, key=lambda x: x["sweetness"], reverse=order_by == "DESC")
    assert [{"id": row["id"], "sweetness": row["sweetness"]} for row in result.data["fruits"]] == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"])
@pytest.mark.snapshot
async def test_nulls(
    order_by: Literal["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"],
    any_query: AnyQueryExecutor,
    raw_users: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(f"{{ users(orderBy: {{ bio: {order_by} }}) {{ id bio }} }}"))
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [{"id": row["id"], "bio": row["bio"]} for row in raw_users if row["bio"] is not None]
    nulls = [{"id": row["id"], "bio": row["bio"]} for row in raw_users if row["bio"] is None]
    expected_sort = sorted(expected_sort, key=lambda x: x["bio"], reverse=order_by.startswith("DESC"))
    expected_sort = expected_sort + nulls if order_by.endswith("LAST") else nulls + expected_sort
    actual_sort = [{"id": row["id"], "bio": row["bio"]} for row in result.data["users"]]
    assert actual_sort == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "aggregation",
    ["max", "min", "sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
)
@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by_aggregations(
    order_by: Literal["ASC", "DESC"],
    aggregation: Literal["max", "min", "sum", "avg", "varPop", "stddevPop", "varSamp", "stddevSamp"],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    db_features: DatabaseFeatures,
) -> None:
    if aggregation not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {aggregation} aggregation function")

    result = await maybe_async(
        any_query(
            f"""{{
            colors(orderBy: {{ fruitsAggregate: {{ {aggregation}: {{ waterPercent: {order_by} }} }} }}) {{
                id
                fruits {{
                    waterPercent
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    water_percent_map: dict[str, float | Decimal] = {
        color["id"]: compute_aggregation(
            aggregation, [fruit["water_percent"] for fruit in raw_fruits if fruit["color_id"] == color["id"]]
        )
        for color in raw_colors
    }
    expected_order = sorted(water_percent_map, key=lambda id_: water_percent_map[id_], reverse=order_by == "DESC")
    assert [row["id"] for row in result.data["colors"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_relation_order_by(
    order_by: Literal["ASC", "DESC"],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(
        any_query(
            f"""{{
            colors {{
                id
                fruits(orderBy: {{ sweetness: {order_by} }}) {{
                    sweetness
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = sorted(
            (fruit["sweetness"] for fruit in raw_fruits if fruit["color_id"] == color["id"]), reverse=order_by == "DESC"
        )
        assert [row["sweetness"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_deterministic_ordering(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that list resolvers return ordered results even if no order by is specified."""
    result = await maybe_async(
        any_query(
            """
            {
                colors {
                    id
                    fruits {
                        id
                    }
                }
            }
        """
        )
    )
    assert not result.errors
    assert result.data

    assert result.data["colors"] == [
        {"id": 1, "fruits": [{"id": 1}, {"id": 2}]},
        {"id": 2, "fruits": [{"id": 3}, {"id": 4}, {"id": 5}]},
        {"id": 3, "fruits": [{"id": 6}, {"id": 7}]},
        {"id": 4, "fruits": [{"id": 8}, {"id": 9}]},
        {"id": 5, "fruits": [{"id": 10}, {"id": 11}]},
    ]
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_deterministic_ordering_mixed_with_user_ordering(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that list resolvers return ordered results even if no order by is specified."""
    result = await maybe_async(
        any_query(
            """
            {
                colors(orderBy: { name: ASC }) {
                    id
                    fruits {
                        id
                    }
                }
            }
        """
        )
    )
    assert not result.errors
    assert result.data

    assert result.data["colors"] == [
        {"id": 4, "fruits": [{"id": 8}, {"id": 9}]},
        {"id": 3, "fruits": [{"id": 6}, {"id": 7}]},
        {"id": 5, "fruits": [{"id": 10}, {"id": 11}]},
        {"id": 1, "fruits": [{"id": 1}, {"id": 2}]},
        {"id": 2, "fruits": [{"id": 3}, {"id": 4}, {"id": 5}]},
    ]
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
