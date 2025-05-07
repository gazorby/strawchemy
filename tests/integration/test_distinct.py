from __future__ import annotations

from uuid import uuid4

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.fixture
def raw_colors() -> RawRecordData:
    return [
        {"id": str(uuid4()), "name": "Red"},
        {"id": str(uuid4()), "name": "Red"},
        {"id": str(uuid4()), "name": "Orange"},
        {"id": str(uuid4()), "name": "Orange"},
        {"id": str(uuid4()), "name": "Pink"},
    ]


@pytest.mark.snapshot
async def test_distinct(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ colors(distinctOn: [name]) { id name } }"))
    assert not result.errors
    assert result.data

    assert {color["name"] for color in result.data["colors"]} == {"Red", "Orange", "Pink"}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
