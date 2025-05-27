from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy import Insert, MetaData, insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.fixtures import QueryTracker
from tests.integration.models import DateTimeModel, date_time_metadata
from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


@pytest.fixture
def metadata() -> MetaData:
    return date_time_metadata


@pytest.fixture
def seed_insert_statements(raw_date_times: RawRecordData) -> list[Insert]:
    return [insert(DateTimeModel).values(raw_date_times)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.DateTimeAsyncQuery
    if dialect == "mysql":
        return mysql_types.DateTimeAsyncQuery
    if dialect == "sqlite":
        return sqlite_types.DateTimeAsyncQuery
    pytest.skip(f"Date/Time tests can't be run on this dialect: {dialect}")


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.DateTimeSyncQuery
    if dialect == "mysql":
        return mysql_types.DateTimeSyncQuery
    if dialect == "sqlite":
        return sqlite_types.DateTimeSyncQuery
    pytest.skip(f"Date/Time tests can't be run on this dialect: {dialect}")


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
    raw_date_times: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
        {{
            dateTimes(filter: {{ dateCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                id
                dateCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["dateTimes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["dateTimes"][i]["id"] == raw_date_times[expected_id]["id"]
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
    raw_date_times: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
        {{
            dateTimes(filter: {{ timeCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                id
                timeCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["dateTimes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["dateTimes"][i]["id"] == raw_date_times[expected_id]["id"]
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
    raw_date_times: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
        {{
            dateTimes(filter: {{ datetimeCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                id
                datetimeCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["dateTimes"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["dateTimes"][i]["id"] == raw_date_times[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
