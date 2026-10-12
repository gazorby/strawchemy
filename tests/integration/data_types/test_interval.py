from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import msgspec
import pytest
import strawberry
from sqlalchemy import Insert, MetaData, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import IntervalModel, IntervalParentModel, interval_metadata
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.typing import SupportedDialect


seconds_in_year = 60 * 60 * 24 * 365.25
seconds_in_month = seconds_in_year / 12
seconds_in_day = 60 * 60 * 24


_PARENTS: RawRecordData = [{"id": 1}, {"id": 2}]
_INTERVALS: RawRecordData = [
    {"id": 1, "time_delta_col": timedelta(days=2, hours=23, minutes=59, seconds=59), "parent_id": 2},
    {"id": 2, "time_delta_col": timedelta(weeks=1, days=3, hours=12), "parent_id": 1},
    {"id": 3, "time_delta_col": timedelta(seconds=1), "parent_id": 2},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.filter(IntervalModel, include=["time_delta_col"])
    class IntervalFilter: ...

    @strawchemy.type(IntervalModel, include=["id", "time_delta_col"])
    class IntervalType: ...

    @strawchemy.aggregate(IntervalModel, include=["time_delta_col"])
    class IntervalAggregation: ...

    @strawchemy.type(IntervalParentModel, include="all")
    class IntervalParentType: ...

    @strawchemy.filter(IntervalParentModel, include="all")
    class IntervalParentFilter: ...

    @strawchemy.order(IntervalParentModel, include="all")
    class IntervalParentOrder: ...

    @strawberry.type
    class Query:
        intervals: list[IntervalType] = strawchemy.field(filter_input=IntervalFilter)
        interval_aggregations: IntervalAggregation = strawchemy.field(root_aggregations=True)
        interval_parents: list[IntervalParentType] = strawchemy.field(
            filter_input=IntervalParentFilter, order_by_input=IntervalParentOrder
        )

    return Operations(query=Query)


def _encode(value: timedelta) -> str:
    return msgspec.json.encode(value).decode()


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def metadata() -> MetaData:
    return interval_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(IntervalParentModel).values(_PARENTS), insert(IntervalModel).values(_INTERVALS)]


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


@pytest.fixture
def native_interval(db_features: DatabaseFeatures) -> None:
    if not db_features.supports_native_interval:
        pytest.skip(f"{db_features.dialect} cannot sum intervals")


@pytest.mark.usefixtures("native_interval")
async def test_sum_output(any_async_query: AnyQueryExecutor) -> None:
    """Test that root and nested sum aggregations over an interval column return the summed duration."""
    query = """
        {
            intervalAggregations { aggregations { sum { timeDeltaCol } } }
            intervalParents { id childrenAggregate { sum { timeDeltaCol } } }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["intervalAggregations"]["aggregations"]["sum"]["timeDeltaCol"] == _encode(
        timedelta(days=13, hours=12)
    )
    assert {
        parent["id"]: parent["childrenAggregate"]["sum"]["timeDeltaCol"] for parent in result.data["intervalParents"]
    } == {1: _encode(timedelta(days=10, hours=12)), 2: _encode(timedelta(days=3))}


@pytest.mark.usefixtures("native_interval")
async def test_sum_interval_order_by(any_async_query: AnyQueryExecutor) -> None:
    """Test that ordering by the sum of an interval column sorts parents by their summed duration."""
    query = "{ intervalParents(orderBy: { childrenAggregate: { sumInterval: { timeDeltaCol: ASC } } }) { id } }"
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert [parent["id"] for parent in result.data["intervalParents"]] == [2, 1]


@pytest.mark.parametrize(
    "predicate",
    [
        pytest.param(f"{{ gt: {msgspec.json.encode(_encode(timedelta(days=5))).decode()} }}", id="duration"),
        pytest.param("{ days: { gt: 5 } }", id="days"),
    ],
)
@pytest.mark.usefixtures("native_interval")
async def test_sum_interval_filter(predicate: str, any_async_query: AnyQueryExecutor) -> None:
    """Test that filtering on the sum of an interval column keeps parents whose summed duration exceeds 5 days."""
    query = f"""
        {{
            intervalParents(
                filter: {{
                    childrenAggregate: {{ sumInterval: {{ arguments: [timeDeltaCol], predicate: {predicate} }} }}
                }}
            ) {{ id }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert [parent["id"] for parent in result.data["intervalParents"]] == [1]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ intervalAggregations { aggregations { sum { timeDeltaCol } } } }", id="output"),
        pytest.param(
            "{ intervalParents(orderBy: { childrenAggregate: { sumInterval: { timeDeltaCol: ASC } } }) { id } }",
            id="order-by",
        ),
        pytest.param(
            "{ intervalParents(filter: { childrenAggregate: { sumInterval: { arguments: [timeDeltaCol], "
            'predicate: { gt: "P5D" } } } }) { id } }',
            id="filter",
        ),
    ],
)
async def test_sum_interval_not_offered_without_native_interval(
    query: str, any_async_query: AnyQueryExecutor, db_features: DatabaseFeatures
) -> None:
    """Test that a dialect without native intervals rejects sums over interval columns at validation."""
    if db_features.supports_native_interval:
        pytest.skip(f"{db_features.dialect} can sum intervals")
    result = await maybe_async(any_async_query(query))
    assert result.errors
    assert result.data is None
