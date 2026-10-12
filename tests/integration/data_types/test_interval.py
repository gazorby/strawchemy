from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import msgspec
import pytest
import strawberry
from sqlalchemy import Insert, MetaData, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import IntervalModel, interval_metadata
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect


seconds_in_year = 60 * 60 * 24 * 365.25
seconds_in_month = seconds_in_year / 12
seconds_in_day = 60 * 60 * 24


_INTERVALS: RawRecordData = [
    {"id": 1, "time_delta_col": timedelta(days=2, hours=23, minutes=59, seconds=59)},
    {"id": 2, "time_delta_col": timedelta(weeks=1, days=3, hours=12)},
    {"id": 3, "time_delta_col": timedelta(seconds=1)},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.filter(IntervalModel, include=["time_delta_col"])
    class IntervalFilter: ...

    @strawchemy.type(IntervalModel, include=["id", "time_delta_col"])
    class IntervalType: ...

    @strawberry.type
    class Query:
        intervals: list[IntervalType] = strawchemy.field(filter_input=IntervalFilter)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def metadata() -> MetaData:
    return interval_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(IntervalModel).values(_INTERVALS)]


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
    any_async_query: AnyQueryExecutor,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["intervals"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["intervals"][i]["id"] == _INTERVALS[expected_id]["id"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_timedelta_output(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            intervals {
                id
                timeDeltaCol
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["intervals"]) == len(_INTERVALS)

    for interval in result.data["intervals"]:
        expected_interval = next(f for f in _INTERVALS if f["id"] == interval["id"])
        assert interval["timeDeltaCol"] == msgspec.json.encode(expected_interval["time_delta_col"]).decode()

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "dto_filter",
    [
        pytest.param("{ timeDeltaCol: { days: null } }", id="part"),
        pytest.param("{ timeDeltaCol: { hours: { eq: null } } }", id="part-operator"),
        pytest.param("{ _not: { timeDeltaCol: { seconds: { gt: null }, lt: null } } }", id="not-part-operator"),
    ],
)
async def test_null_part_operator_is_ignored(dto_filter: str, any_async_query: AnyQueryExecutor) -> None:
    """Test that an interval part, or one of its operators, set to null is ignored."""
    result = await maybe_async(any_async_query(f"{{ intervals(filter: {dto_filter}) {{ id }} }}"))
    assert not result.errors
    assert result.data
    assert sorted(row["id"] for row in result.data["intervals"]) == sorted(row["id"] for row in _INTERVALS)
