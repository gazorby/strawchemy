from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

if TYPE_CHECKING:
    from strawchemy import StrawchemyConfig


@pytest.fixture
def raw_colors() -> RawRecordData:
    return [
        {"id": 1, "name": "Red"},
        {"id": 2, "name": "Red"},
        {"id": 3, "name": "Orange"},
        {"id": 4, "name": "Orange"},
        {"id": 5, "name": "Pink"},
    ]


@pytest.mark.parametrize(
    "deterministic_ordering",
    [pytest.param(True, id="deterministic-ordering"), pytest.param(False, id="non-deterministic-ordering")],
)
@pytest.mark.snapshot
async def test_distinct_on(
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    config: StrawchemyConfig,
    deterministic_ordering: bool,
) -> None:
    config.deterministic_ordering = deterministic_ordering
    result = await maybe_async(any_query("{ colors(distinctOn: [name]) { id name } }"))
    assert not result.errors
    assert result.data

    expected = [{"id": 1, "name": "Red"}, {"id": 3, "name": "Orange"}, {"id": 5, "name": "Pink"}]
    assert all(color in result.data["colors"] for color in expected)

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_distinct_and_order_by(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query("{ colors(distinctOn: [name], orderBy: [{name: ASC}, {id: DESC}]) { id name } }")
    )
    assert not result.errors
    assert result.data

    expected = [{"id": 2, "name": "Red"}, {"id": 4, "name": "Orange"}, {"id": 5, "name": "Pink"}]
    assert all(color in result.data["colors"] for color in expected)

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
