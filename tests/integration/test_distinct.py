from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect


@pytest.fixture
def raw_colors() -> RawRecordData:
    return [
        {"id": 1, "name": "Red"},
        {"id": 2, "name": "Red"},
        {"id": 3, "name": "Orange"},
        {"id": 4, "name": "Orange"},
        {"id": 5, "name": "Pink"},
    ]


@pytest.mark.snapshot
async def test_distinct(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion, dialect: SupportedDialect
) -> None:
    if dialect != "postgresql":
        pytest.skip(f"Distinct argument not available on {dialect}")
    result = await maybe_async(any_query("{ colors(distinctOn: [name]) { id name } }"))
    assert not result.errors
    assert result.data

    assert {color["name"] for color in result.data["colors"]} == {"Red", "Orange", "Pink"}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
