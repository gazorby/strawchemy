from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Literal

import pytest

from strawchemy.schema.pagination import DefaultOffsetPagination
from tests.integration.fixtures import QueryTracker
from tests.integration.models import Fruit
from tests.integration.typing import RawRecordData
from tests.integration.utils import compute_aggregation, from_graphql_representation, python_type
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy.config.databases import DatabaseFeatures

pytestmark = [pytest.mark.integration]


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
            color(id: {raw_colors[0]["id"]}) {{
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


async def test_count_aggregation_many_to_many(
    any_query: AnyQueryExecutor, raw_user_departments: RawRecordData, raw_users: RawRecordData
) -> None:
    """Test that a many-to-many count matches the number of join-table rows of each user."""
    result = await maybe_async(
        any_query(
            """
            {
                users {
                    id
                    departmentsAggregate { count }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    departments_per_user = Counter(link["user_id"] for link in raw_user_departments)
    actual = {user["id"]: user["departmentsAggregate"]["count"] for user in result.data["users"]}
    assert actual == {user["id"]: departments_per_user[user["id"]] for user in raw_users}


async def test_count_aggregation_many_to_many_join_predicates(
    any_query: AnyQueryExecutor,
    raw_user_departments: RawRecordData,
    raw_users: RawRecordData,
    raw_departments: RawRecordData,
) -> None:
    """Test that a many-to-many count honours the relationship primaryjoin and secondaryjoin predicates."""
    result = await maybe_async(
        any_query(
            """
            {
                users {
                    id
                    filteredDepartmentsAggregate { count }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    user_names = {user["id"]: user["name"] for user in raw_users}
    department_names = {department["id"]: department["name"] for department in raw_departments}
    joined = Counter(
        link["user_id"]
        for link in raw_user_departments
        if user_names[link["user_id"]] != "Bob" and department_names[link["department_id"]] != "IT"
    )
    actual = {user["id"]: user["filteredDepartmentsAggregate"]["count"] for user in result.data["users"]}
    assert actual == {user["id"]: joined[user["id"]] for user in raw_users}


async def test_count_aggregation_many_to_many_nested(
    any_query: AnyQueryExecutor, raw_user_departments: RawRecordData
) -> None:
    """Test that a nested many-to-many count matches the number of users of each department."""
    result = await maybe_async(
        any_query(
            """
            {
                users {
                    id
                    departments {
                        id
                        usersAggregate { count }
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    users_per_department = Counter(link["department_id"] for link in raw_user_departments)
    departments_per_user = Counter(link["user_id"] for link in raw_user_departments)
    # A nested aggregate rides on the flat result row, so its value can only be attributed
    # unambiguously to a department when the user holds exactly one.
    actual = {
        department["id"]: department["usersAggregate"]["count"]
        for user in result.data["users"]
        if departments_per_user[user["id"]] == 1
        for department in user["departments"]
    }
    assert actual == {
        link["department_id"]: users_per_department[link["department_id"]]
        for link in raw_user_departments
        if departments_per_user[link["user_id"]] == 1
    }


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
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
            color(id: {raw_colors[0]["id"]}) {{
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

    assert pytest.approx(actual_sum) == expected_sum

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
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
            color(id: {raw_colors[0]["id"]}) {{
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
            color(id: {raw_colors[0]["id"]}) {{
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
    ["avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
)
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
    ],
)
@pytest.mark.snapshot
async def test_statistical_aggregation(
    agg_type: Literal["avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    db_features: DatabaseFeatures,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    if agg_type not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {agg_type} aggregation function")

    query = f"""
        {{
            color(id: {raw_colors[0]["id"]}) {{
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
@pytest.mark.parametrize("agg_type", ["sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"])
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
    ],
)
@pytest.mark.snapshot
async def test_root_aggregation(
    agg_type: Literal["sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    pagination: DefaultOffsetPagination | None,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    db_features: DatabaseFeatures,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    if agg_type not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {agg_type} aggregation function")

    query_name = "fruitAggregations" if pagination is None else "fruitAggregationsPaginatedLimit2"
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

    rel = (
        0.0001 if db_features.dialect == "mysql" and field_name == "sweetness" and agg_type in ("avg", "sum") else None
    )
    assert actual_value == pytest.approx(expected_value, rel=rel)

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
