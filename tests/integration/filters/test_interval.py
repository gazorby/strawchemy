from __future__ import annotations

from datetime import timedelta

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import Insert, MetaData, insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.fixtures import QueryTracker
from tests.integration.models import IntervalModel, interval_metadata
from tests.integration.types import IntervalFilter, IntervalType, strawchemy
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

seconds_in_year = 60 * 60 * 24 * 365.25
seconds_in_month = seconds_in_year / 12
seconds_in_day = 60 * 60 * 24


@strawberry.type
class AsyncQuery:
    intervals: list[IntervalType] = strawchemy.field(
        filter_input=IntervalFilter, repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncQuery:
    intervals: list[IntervalType] = strawchemy.field(
        filter_input=IntervalFilter, repository_type=StrawchemySyncRepository
    )


@pytest.fixture
def metadata() -> MetaData:
    return interval_metadata


@pytest.fixture
def seed_insert_statements(raw_intervals: RawRecordData) -> list[Insert]:
    return [insert(IntervalModel).values(raw_intervals)]


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


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
    raw_intervals: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
            {{
                intervals(filter: {{ timeDeltaCol: {{ {component}: {{ eq: {value} }} }} }}) {{
                    id
                    timeDeltaCol
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["intervals"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["intervals"][i]["id"] == raw_intervals[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
