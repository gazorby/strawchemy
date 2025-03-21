from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .models import SQLDataTypes, SQLDataTypesContainer
from .types import SQLDataTypesContainerFilter, SQLDataTypesContainerType, strawchemy
from .typing import RawRecordData

if TYPE_CHECKING:
    from sqlalchemy import Insert

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        filter_input=SQLDataTypesContainerFilter, repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncQuery:
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        filter_input=SQLDataTypesContainerFilter, repository_type=StrawchemySyncRepository
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.fixture
def raw_containers() -> RawRecordData:
    return [{"id": str(uuid4())}, {"id": str(uuid4())}]


@pytest.fixture
def seed_insert_statements(
    raw_containers: RawRecordData, raw_sql_data_types_set1: RawRecordData, raw_sql_data_types_set2: RawRecordData
) -> list[Insert]:
    return [
        insert(SQLDataTypesContainer).values(raw_containers),
        insert(SQLDataTypes).values(raw_sql_data_types_set1),
        insert(SQLDataTypes).values(raw_sql_data_types_set2),
    ]


@pytest.mark.parametrize(
    ("predicate", "value", "expected_container_indices"),
    [
        pytest.param("eq", 2, [0, 1], id="eq-match"),
        pytest.param("neq", 0, [0, 1], id="neq-match"),
        pytest.param("gt", 1, [0, 1], id="gt-match"),
        pytest.param("gte", 2, [0, 1], id="gte-match"),
        pytest.param("lt", 3, [0, 1], id="lt-match"),
        pytest.param("lte", 2, [0, 1], id="lte-match"),
        pytest.param("in", [1, 2, 3], [0, 1], id="in-match"),
        pytest.param("nin", [0, 3, 4], [0, 1], id="nin-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter(
    predicate: str,
    value: int | list[int],
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation."""
    # Prepare the value for GraphQL query
    value_str = f"[{', '.join(str(v) for v in value)}]" if isinstance(value, list) else str(value)

    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    count: {{
                        arguments: [id]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_container_indices"),
    [
        pytest.param("strCol", "eq", "another set 1 string", [0], id="eq-match"),
        pytest.param("strCol", "like", "%set 1%", [0], id="like-match"),
        pytest.param("strCol", "ilike", "%SET 1%", [0], id="ilike-match"),
        pytest.param("strCol", "startswith", "another set 1", [0], id="startswith-match"),
        pytest.param("strCol", "contains", "set 1", [0], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_min_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by minString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    minString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_container_indices"),
    [
        pytest.param("strCol", "eq", "data set 1 string", [0], id="eq-match"),
        pytest.param("strCol", "like", "%set 1%", [0], id="like-match"),
        pytest.param("strCol", "ilike", "%SET 1%", [0], id="ilike-match"),
        pytest.param("strCol", "startswith", "data set 1", [0], id="startswith-match"),
        pytest.param("strCol", "contains", "set 1", [0], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_max_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by maxString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    maxString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_container_indices"),
    [
        pytest.param("intCol", "eq", 175, [0], id="int-eq-match"),
        pytest.param("intCol", "gt", 175, [1], id="int-gt-match"),
        pytest.param("floatCol", "eq", 12.75, [0], id="float-eq-match"),
        pytest.param("floatCol", "gt", 13.0, [1], id="float-gt-match"),
        pytest.param("decimalCol", "eq", 126.25, [0], id="decimal-eq-match"),
        pytest.param("decimalCol", "gt", 130.0, [1], id="decimal-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by sum aggregation."""
    value_str = str(value)

    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    sum: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_container_indices"),
    [
        pytest.param("intCol", "eq", 87.5, [0], id="int-avg-eq-match"),
        pytest.param("intCol", "gt", 90.0, [1], id="int-avg-gt-match"),
        pytest.param("floatCol", "eq", 6.375, [0], id="float-avg-eq-match"),
        pytest.param("floatCol", "gt", 11.0, [1], id="float-avg-gt-match"),
        pytest.param("decimalCol", "eq", 63.125, [0], id="decimal-avg-eq-match"),
        pytest.param("decimalCol", "gt", 65.0, [1], id="decimal-avg-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_avg_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by avg aggregation."""
    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    avg: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("distinct", "expected_count", "expected_container_indices"),
    [
        pytest.param(True, 1, [0], id="distinct-match"),
        pytest.param(False, 2, [0, 1], id="non-distinct-match"),
        pytest.param(None, 2, [0, 1], id="default-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter_with_distinct(
    distinct: bool | None,
    expected_count: int,
    expected_container_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_containers: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation with distinct option."""
    distinct_str = f"distinct: {to_graphql_representation(distinct, 'input')}" if distinct is not None else ""

    query = f"""
        {{
            containers(filter: {{
                dataTypesAggregate: {{
                    count: {{
                        arguments: [optionalStrCol]
                        predicate: {{ eq: {expected_count} }}
                        {distinct_str}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["containers"]) == len(expected_container_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["containers"]}

    # Get the expected container IDs
    expected_container_ids = {raw_containers[idx]["id"] for idx in expected_container_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
