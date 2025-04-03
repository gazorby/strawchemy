from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.types import DefaultOffsetPagination

import strawberry
from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import SQLDataTypesFilter, SQLDataTypesType, strawchemy
from .typing import RawRecordData
from .utils import to_graphql_representation

pytestmark = [pytest.mark.integration]

seconds_in_year = 60 * 60 * 24 * 365.25
seconds_in_month = seconds_in_year / 12
seconds_in_day = 60 * 60 * 24


@strawberry.type
class AsyncQuery:
    sql_data_types: list[SQLDataTypesType] = strawchemy.field(
        filter_input=SQLDataTypesFilter, repository_type=StrawchemyAsyncRepository
    )
    data_types_paginated: list[SQLDataTypesType] = strawchemy.field(
        filter_input=SQLDataTypesFilter,
        pagination=DefaultOffsetPagination(limit=1),
        repository_type=StrawchemyAsyncRepository,
    )


@strawberry.type
class SyncQuery:
    sql_data_types: list[SQLDataTypesType] = strawchemy.field(
        filter_input=SQLDataTypesFilter, repository_type=StrawchemySyncRepository
    )
    data_types_paginated: list[SQLDataTypesType] = strawchemy.field(
        filter_input=SQLDataTypesFilter,
        pagination=DefaultOffsetPagination(limit=1),
        repository_type=StrawchemySyncRepository,
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.mark.snapshot
async def test_no_filtering(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query("{ sqlDataTypes { id } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(raw_sql_data_types)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        pytest.param("strCol", "test string", id="str"),
        pytest.param("intCol", 42, id="int"),
        pytest.param("floatCol", 3.14159, id="float"),
        pytest.param("decimalCol", Decimal("123.45"), id="decimal"),
        pytest.param("boolCol", True, id="bool"),
        pytest.param("timeCol", time(14, 30, 45), id="time"),
        pytest.param("dateCol", date(2023, 1, 15), id="date"),
        pytest.param("datetimeCol", datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC), id="datetime"),
        pytest.param("timeDeltaCol", timedelta(days=2, hours=23, minutes=59, seconds=59), id="timedelta"),
        pytest.param("dictCol", {"key1": "value1", "key2": 2, "nested": {"inner": "value"}}, id="dict"),
    ],
)
@pytest.mark.snapshot
async def test_eq(
    field_name: str,
    value: Any,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ eq: {value} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(
        any_query(query.format(field_name=field_name, value=to_graphql_representation(value, "input")))
    )
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 1
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[0]["id"]
    assert result.data["sqlDataTypes"][0][field_name] == to_graphql_representation(value, "output")
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        pytest.param("strCol", "test string", id="str"),
        pytest.param("intCol", 42, id="int"),
        pytest.param("floatCol", 3.14159, id="float"),
        pytest.param("decimalCol", Decimal("123.45"), id="decimal"),
        pytest.param("boolCol", True, id="bool"),
        pytest.param("timeCol", time(14, 30, 45), id="time"),
        pytest.param("dateCol", date(2023, 1, 15), id="date"),
        pytest.param("datetimeCol", datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC), id="datetime"),
        pytest.param("timeDeltaCol", timedelta(days=2, hours=23, minutes=59, seconds=59), id="timedelta"),
        pytest.param("dictCol", {"key1": "value1", "key2": 2, "nested": {"inner": "value"}}, id="dict"),
    ],
)
@pytest.mark.snapshot
async def test_neq(
    field_name: str,
    value: Any,
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ neq: {value} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(
        any_query(query.format(field_name=field_name, value=to_graphql_representation(value, "input")))
    )
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 2
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[1]["id"]
    assert result.data["sqlDataTypes"][1]["id"] == raw_sql_data_types[2]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_isnull(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                sqlDataTypes(filter: { optionalStrCol: { isNull: true } }) {
                    id
                    optionalStrCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 1
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[2]["id"]
    assert result.data["sqlDataTypes"][0]["optionalStrCol"] is None
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for in and nin filters
@pytest.mark.parametrize(
    ("field_name", "values", "expected_ids"),
    [
        pytest.param("strCol", ["test string", "another STRING"], [0, 1], id="str"),
        pytest.param("intCol", [42, -10], [0, 1], id="int"),
        pytest.param("floatCol", [3.14159, 2.71828], [0, 1], id="float"),
        pytest.param("decimalCol", [Decimal("123.45"), Decimal("-99.99")], [0, 1], id="decimal"),
        pytest.param("boolCol", [True, False], [0, 1, 2], id="bool"),
        pytest.param("dateCol", [date(2023, 1, 15), date(2022, 12, 31)], [0, 1], id="date"),
        pytest.param("timeCol", [time(14, 30, 45), time(8, 15, 0)], [0, 1], id="time"),
        pytest.param(
            "datetimeCol",
            [
                datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC),
                datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC),
            ],
            [0, 1],
            id="datetime",
        ),
        pytest.param(
            "timeDeltaCol",
            [
                timedelta(days=2, hours=23, minutes=59, seconds=59),
                timedelta(weeks=1, days=3, hours=12),
            ],
            [0, 1],
            id="timedelta",
        ),
    ],
)
@pytest.mark.snapshot
async def test_in(
    field_name: str,
    values: list[Any],
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    values_str = ", ".join(str(to_graphql_representation(value, "input")) for value in values)
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ in: [{values_str}] }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    assert {result.data["sqlDataTypes"][i]["id"] for i in range(len(expected_ids))} == {
        raw_sql_data_types[i]["id"] for i in expected_ids
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "values", "expected_ids"),
    [
        pytest.param("strCol", ["test string", "another STRING"], [2], id="str"),
        pytest.param("intCol", [42, -10], [2], id="int"),
        pytest.param("floatCol", [3.14159, 2.71828], [2], id="float"),
        pytest.param("decimalCol", [Decimal("123.45"), Decimal("-99.99")], [2], id="decimal"),
        pytest.param("boolCol", [True, False], [], id="bool"),
        pytest.param("dateCol", [date(2023, 1, 15), date(2022, 12, 31)], [2], id="date"),
        pytest.param("timeCol", [time(14, 30, 45), time(8, 15, 0)], [2], id="time"),
        pytest.param(
            "datetimeCol",
            [
                datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC),
                datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC),
            ],
            [2],
            id="datetime",
        ),
        pytest.param(
            "timeDeltaCol",
            [
                timedelta(days=2, hours=23, minutes=59, seconds=59),
                timedelta(weeks=1, days=3, hours=12),
            ],
            [2],
            id="timedelta",
        ),
    ],
)
@pytest.mark.snapshot
async def test_nin(
    field_name: str,
    values: list[Any],
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    values_str = ", ".join(str(to_graphql_representation(value, "input")) for value in values)
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ nin: [{values_str}] }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    assert {result.data["sqlDataTypes"][i]["id"] for i in range(len(expected_ids))} == {
        raw_sql_data_types[i]["id"] for i in expected_ids
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for gt, gte, lt, lte filters for numeric and date/time types
@pytest.mark.parametrize(
    ("field_name", "value", "expected_ids"),
    [
        pytest.param("intCol", 0, [0], id="int-gt"),
        pytest.param("floatCol", 2.0, [0, 1], id="float-gt"),
        pytest.param("decimalCol", Decimal("0.00"), [0], id="decimal-gt"),
        pytest.param("dateCol", date(2023, 1, 1), [0, 2], id="date-gt"),
        pytest.param("timeCol", time(10, 0, 0), [0], id="time-gt"),
        pytest.param("datetimeCol", datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC), [0, 2], id="datetime-gt"),
        pytest.param("timeDeltaCol", timedelta(days=1), [0, 1], id="timedelta-gt"),
        pytest.param("strCol", "az", [0], id="str-gt"),
    ],
)
@pytest.mark.snapshot
async def test_gt(
    field_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ gt: {to_graphql_representation(value, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "value", "expected_ids"),
    [
        pytest.param("intCol", 0, [0, 2], id="int-gte"),
        pytest.param("floatCol", 2.71828, [0, 1], id="float-gte"),
        pytest.param("decimalCol", Decimal("0.00"), [0, 2], id="decimal-gte"),
        pytest.param("dateCol", date(2023, 1, 15), [0, 2], id="date-gte"),
        pytest.param("timeCol", time(8, 15, 0), [0, 1], id="time-gte"),
        pytest.param("datetimeCol", datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC), [0, 2], id="datetime-gte"),
        pytest.param("timeDeltaCol", timedelta(weeks=1, days=3, hours=12), [1], id="timedelta-gte"),
        pytest.param("strCol", "test string", [0], id="str-gte"),
    ],
)
@pytest.mark.snapshot
async def test_gte(
    field_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ gte: {to_graphql_representation(value, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "value", "expected_ids"),
    [
        pytest.param("intCol", 0, [1], id="int-lt"),
        pytest.param("floatCol", 3.0, [1, 2], id="float-lt"),
        pytest.param("decimalCol", Decimal("100.00"), [1, 2], id="decimal-lt"),
        pytest.param("dateCol", date(2023, 1, 15), [1], id="date-lt"),
        pytest.param("timeCol", time(14, 0, 0), [1, 2], id="time-lt"),
        pytest.param("datetimeCol", datetime(2023, 1, 15, 0, 0, 0, tzinfo=UTC), [1], id="datetime-lt"),
        pytest.param("timeDeltaCol", timedelta(days=7), [0, 2], id="timedelta-lt"),
        pytest.param("strCol", "bbbb", [1, 2], id="str-lt"),
    ],
)
@pytest.mark.snapshot
async def test_lt(
    field_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ lt: {to_graphql_representation(value, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "value", "expected_ids"),
    [
        pytest.param("intCol", 0, [1, 2], id="int-lte"),
        pytest.param("floatCol", 3.14159, [0, 1, 2], id="float-lte"),
        pytest.param("decimalCol", Decimal("123.45"), [0, 1, 2], id="decimal-lte"),
        pytest.param("dateCol", date(2023, 1, 15), [0, 1], id="date-lte"),
        pytest.param("timeCol", time(14, 30, 45), [0, 1, 2], id="time-lte"),
        pytest.param("datetimeCol", datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC), [0, 1], id="datetime-lte"),
        pytest.param("timeDeltaCol", timedelta(days=2, hours=23, minutes=59, seconds=59), [0, 2], id="timedelta-lte"),
        pytest.param("strCol", "", [2], id="str-lte"),
    ],
)
@pytest.mark.snapshot
async def test_lte(
    field_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ {field_name}: {{ lte: {to_graphql_representation(value, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for string-specific filters
@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("like", "%string%", [0], id="like"),
        pytest.param("nlike", "%string%", [1, 2], id="nlike"),
        pytest.param("ilike", "%STRING%", [0, 1], id="ilike"),
        pytest.param("nilike", "%STRING%", [2], id="nilike"),
        pytest.param("startswith", "test", [0], id="startswith"),
        pytest.param("endswith", "string", [0], id="endswith"),
        pytest.param("contains", "string", [0], id="contains"),
        pytest.param("istartswith", "TEST", [0], id="istartswith"),
        pytest.param("iendswith", "STRING", [0, 1], id="iendswith"),
        pytest.param("icontains", "STRING", [0, 1], id="icontains"),
        pytest.param("regexp", "^test", [0], id="regexp"),
        pytest.param("iregexp", ".*string$", [0, 1], id="iregexp"),
        pytest.param("nregexp", "^test", [1, 2], id="nregexp"),
        pytest.param("inregexp", ".*string$", [2], id="inregexp"),
    ],
)
@pytest.mark.snapshot
async def test_string_filters(
    filter_name: str,
    value: str,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ strCol: {{ {filter_name}: {to_graphql_representation(value, "input")} }} }}) {{
                    id
                    strCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for JSON-specific filters
@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("contains", {"key1": "value1"}, [0], id="contains"),
        pytest.param(
            "containedIn",
            {"key1": "value1", "key2": 2, "nested": {"inner": "value"}, "extra": "value"},
            [0, 2],
            id="containedIn",
        ),
        pytest.param("hasKey", "key1", [0], id="hasKey"),
        pytest.param("hasKeyAll", ["key1", "key2"], [0], id="hasKeyAll"),
        pytest.param("hasKeyAny", ["key1", "status"], [0, 1], id="hasKeyAny"),
    ],
)
@pytest.mark.snapshot
async def test_json_filters(
    filter_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    if isinstance(value, list):
        value_str = ", ".join(to_graphql_representation(v, "input") for v in value)
        value_repr = f"[{value_str}]"
    else:
        value_repr = to_graphql_representation(value, "input")

    query = f"""
            {{
                sqlDataTypes(filter: {{ dictCol: {{ {filter_name}: {value_repr} }} }}) {{
                    id
                    dictCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for array-specific filters
@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("contains", ["one", "two"], [0], id="contains"),
        pytest.param("containedIn", ["one", "two", "three", "four"], [0, 2], id="containedIn"),
        pytest.param("overlap", ["one", "apple"], [0, 1], id="overlap"),
    ],
)
@pytest.mark.snapshot
async def test_postgres_array_filters(
    filter_name: str,
    value: list[str],
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    value_str = ", ".join(to_graphql_representation(v, "input") for v in value)
    query = f"""
            {{
                sqlDataTypes(filter: {{ arrayStrCol: {{ {filter_name}: [{value_str}] }} }}) {{
                    id
                    arrayStrCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for date/time component filters
@pytest.mark.parametrize(
    ("component", "value", "expected_ids"),
    [
        pytest.param("year", 2023, [0], id="year"),
        pytest.param("month", 1, [0], id="month"),
        pytest.param("day", 15, [0], id="day"),
        pytest.param("weekDay", 6, [1], id="weekDay"),  # Sunday is 6
        pytest.param("week", 2, [0], id="week"),  # Second week of the year
        pytest.param("quarter", 1, [0, 2], id="quarter"),  # First quarter
        pytest.param("isoYear", 2023, [0], id="isoYear"),
        pytest.param("isoWeekDay", 7, [0], id="isoWeekDay"),  # Sunday is 7 in ISO
    ],
)
@pytest.mark.snapshot
async def test_date_components(
    component: str,
    value: int,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ dateCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                    id
                    dateCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("component", "value", "expected_ids"),
    [
        pytest.param("hour", 14, [0], id="hour"),
        pytest.param("minute", 30, [0], id="minute"),
        pytest.param("second", 45, [0], id="second"),
    ],
)
@pytest.mark.snapshot
async def test_time_components(
    component: str,
    value: int,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ timeCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                    id
                    timeCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("component", "value", "expected_ids"),
    [
        pytest.param("hour", 14, [0], id="hour"),
        pytest.param("minute", 30, [0], id="minute"),
        pytest.param("second", 45, [0], id="second"),
        pytest.param("year", 2023, [0], id="year"),
        pytest.param("month", 1, [0], id="month"),
        pytest.param("day", 15, [0], id="day"),
        pytest.param("weekDay", 6, [1], id="weekDay"),  # Sunday is 0, saturday is 6
        pytest.param("week", 2, [0], id="week"),
        pytest.param("quarter", 1, [0, 2], id="quarter"),
        pytest.param("isoYear", 2023, [0], id="isoYear"),
        pytest.param("isoWeekDay", 7, [0], id="isoWeekDay"),
    ],
)
@pytest.mark.snapshot
async def test_datetime_components(
    component: str,
    value: int,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ datetimeCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                    id
                    datetimeCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("component", "value", "expected_ids"),
    [
        pytest.param("days", timedelta(weeks=1, days=3, hours=12).total_seconds() / seconds_in_day, [1], id="days"),
        pytest.param("hours", timedelta(weeks=1, days=3, hours=12).total_seconds() / 3600, [1], id="hours"),
        pytest.param("minutes", timedelta(weeks=1, days=3, hours=12).total_seconds() / 60, [1], id="minutes"),
        pytest.param("seconds", timedelta(weeks=1, days=3, hours=12).total_seconds(), [1], id="totalSeconds"),
    ],
)
@pytest.mark.snapshot
async def test_timedelta_components(
    component: str,
    value: int,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                sqlDataTypes(filter: {{ timeDeltaCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                    id
                    timeDeltaCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["sqlDataTypes"][i]["id"] == raw_sql_data_types[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for logical operators
@pytest.mark.snapshot
async def test_and(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                sqlDataTypes(filter: { _and: [
                    { intCol: { gt: 0 } },
                    { strCol: { contains: "string" } }
                ] }) {
                    id
                    intCol
                    strCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 1
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[0]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_or(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                sqlDataTypes(filter: { _or: [
                    { intCol: { eq: 42 } },
                    { intCol: { eq: -10 } }
                ] }) {
                    id
                    intCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 2
    assert {result.data["sqlDataTypes"][0]["id"], result.data["sqlDataTypes"][1]["id"]} == {
        raw_sql_data_types[0]["id"],
        raw_sql_data_types[1]["id"],
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_not(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                sqlDataTypes(filter: { _not: { intCol: { eq: 0 } } }) {
                    id
                    intCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 2
    assert {result.data["sqlDataTypes"][0]["id"], result.data["sqlDataTypes"][1]["id"]} == {
        raw_sql_data_types[0]["id"],
        raw_sql_data_types[1]["id"],
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Test complex nested logical operators
@pytest.mark.snapshot
async def test_complex_logical_operators(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                sqlDataTypes(filter: {
                    _or: [
                        { _and: [
                            { intCol: { gt: 0 } },
                            { strCol: { contains: "string" } }
                        ]},
                        { _and: [
                            { intCol: { lt: 0 } },
                            { _not: { strCol: { eq: "" } } }
                        ]}
                    ]
                }) {
                    id
                    intCol
                    strCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 2
    assert {result.data["sqlDataTypes"][0]["id"], result.data["sqlDataTypes"][1]["id"]} == {
        raw_sql_data_types[0]["id"],
        raw_sql_data_types[1]["id"],
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Test UUID filters
@pytest.mark.snapshot
async def test_uuid_filters(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    uuid_value = raw_sql_data_types[0]["uuid_col"]
    query = f"""
            {{
                sqlDataTypes(filter: {{ uuidCol: {{ eq: "{uuid_value}" }} }}) {{
                    id
                    uuidCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 1
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[0]["id"]
    assert result.data["sqlDataTypes"][0]["uuidCol"] == str(uuid_value)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Test combining multiple filters
async def test_combined_filters(
    any_query: AnyQueryExecutor, raw_sql_data_types: RawRecordData, query_tracker: QueryTracker
) -> None:
    query = """
            {
                sqlDataTypes(filter: {
                    intCol: { gt: -20 },
                    strCol: { contains: "string" },
                    boolCol: { eq: true }
                }) {
                    id
                    intCol
                    strCol
                    boolCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["sqlDataTypes"]) == 1
    assert result.data["sqlDataTypes"][0]["id"] == raw_sql_data_types[0]["id"]
    assert query_tracker.query_count == 1


@pytest.mark.snapshot
async def test_filter_on_paginated_query(
    any_query: AnyQueryExecutor,
    raw_sql_data_types: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
            {
                dataTypesPaginated(filter: { _not: { intCol: { eq: 0 } } }) {
                    id
                    intCol
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["dataTypesPaginated"]) == 1
    assert {result.data["dataTypesPaginated"][0]["id"]} == {raw_sql_data_types[0]["id"]}
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
