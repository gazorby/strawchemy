from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

if TYPE_CHECKING:
    from strawchemy import StrawchemyConfig
    from syrupy.assertion import SnapshotAssertion


@pytest.fixture
def raw_users() -> RawRecordData:
    return [
        {"id": 1, "name": "Alice", "group_id": None, "bio": None},
        {"id": 2, "name": "Alice", "group_id": None, "bio": None},
        {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
        {"id": 4, "name": "Charlie", "group_id": None, "bio": None},
        {"id": 5, "name": "Bob", "group_id": None, "bio": None},
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
    result = await maybe_async(any_query("{ users(distinctOn: [name]) { id name } }"))
    assert not result.errors
    assert result.data

    expected = [{"id": 1, "name": "Alice"}, {"id": 3, "name": "Charlie"}, {"id": 5, "name": "Bob"}]
    assert len(result.data["users"]) == len(expected)
    assert all(user in result.data["users"] for user in expected)

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_distinct_and_order_by(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query("{ users(distinctOn: [name], orderBy: [{name: ASC}, {id: DESC}]) { id name } }")
    )
    assert not result.errors
    assert result.data

    assert result.data["users"] == [{"id": 2, "name": "Alice"}, {"id": 5, "name": "Bob"}, {"id": 4, "name": "Charlie"}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
