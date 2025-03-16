from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.integration.utils import from_graphql_representation, python_type
from tests.typing import AnyQueryExecutor
from tests.unit.models import SQLDataTypes
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import SQLDataTypesContainerType, strawchemy
from .typing import RawRecordData

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    container: SQLDataTypesContainerType = strawchemy.field(repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    container: SQLDataTypesContainerType = strawchemy.field(repository_type=StrawchemySyncRepository)


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.mark.snapshot
async def test_count_aggregation(
    any_query: AnyQueryExecutor,
    raw_sql_data_types_container: RawRecordData,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the count aggregation function."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
                    count
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["container"]["dataTypesAggregate"]["count"] == len(raw_sql_data_types)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("intCol", "int_col"),
        ("floatCol", "float_col"),
        ("decimalCol", "decimal_col"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the sum aggregation function for a specific field."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
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
    expected_sum = sum(record[raw_field_name] for record in raw_sql_data_types)

    # Verify result
    actual_sum = result.data["container"]["dataTypesAggregate"]["sum"][field_name]

    if field_name == "decimalCol":
        assert str(actual_sum) == str(expected_sum)
    else:
        assert pytest.approx(actual_sum) == expected_sum

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("intCol", "int_col"),
        ("floatCol", "float_col"),
        ("decimalCol", "decimal_col"),
        ("strCol", "str_col"),
        ("dateCol", "date_col"),
        ("timeCol", "time_col"),
        ("datetimeCol", "datetime_col"),
    ],
)
@pytest.mark.snapshot
async def test_min_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the min aggregation function for a specific field."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
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
        result.data["container"]["dataTypesAggregate"]["min"][field_name], python_type(SQLDataTypes, raw_field_name)
    )
    assert actual_min is not None

    # For fields where we can calculate expected values, verify them
    expected_min = min(record[raw_field_name] for record in raw_sql_data_types)

    assert actual_min == expected_min

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("intCol", "int_col"),
        ("floatCol", "float_col"),
        ("decimalCol", "decimal_col"),
        ("strCol", "str_col"),
        ("dateCol", "date_col"),
        ("timeCol", "time_col"),
        ("datetimeCol", "datetime_col"),
    ],
)
@pytest.mark.snapshot
async def test_max_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the max aggregation function for a specific field."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
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
        result.data["container"]["dataTypesAggregate"]["max"][field_name], python_type(SQLDataTypes, raw_field_name)
    )
    assert actual_max is not None

    # For fields where we can calculate expected values, verify them
    expected_max = max(record[raw_field_name] for record in raw_sql_data_types)

    assert actual_max == expected_max

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("intCol", "int_col"),
        ("floatCol", "float_col"),
        ("decimalCol", "decimal_col"),
    ],
)
@pytest.mark.snapshot
async def test_avg_aggregation(
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    raw_sql_data_types_container: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the avg aggregation function for a specific field."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
                    avg {{
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
    values = [record[raw_field_name] for record in raw_sql_data_types]
    expected_avg = sum(values) / len(values)

    # Verify result
    actual_avg = from_graphql_representation(
        result.data["container"]["dataTypesAggregate"]["avg"][field_name], python_type(SQLDataTypes, raw_field_name)
    )

    assert pytest.approx(actual_avg) == expected_avg

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "agg_type",
    ["stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
)
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("intCol", "int_col"),
        ("floatCol", "float_col"),
        ("decimalCol", "decimal_col"),
    ],
)
@pytest.mark.snapshot
async def test_statistical_aggregation(
    agg_type: str,
    field_name: str,
    raw_field_name: str,
    any_query: AnyQueryExecutor,
    raw_sql_data_types_container: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    query = f"""
        {{
            container(id: "{raw_sql_data_types_container[0]["id"]}") {{
                dataTypesAggregate {{
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
        result.data["container"]["dataTypesAggregate"][agg_type][field_name], python_type(SQLDataTypes, raw_field_name)
    )

    assert isinstance(actual_value, int | float | Decimal) or actual_value is None

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
