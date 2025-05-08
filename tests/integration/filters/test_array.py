from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy import Insert, MetaData, insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.fixtures import QueryTracker
from tests.integration.models import ArrayModel, array_metadata
from tests.integration.types import postgres as postgres_types
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


@pytest.fixture(name="metadata")
def fx_metadata() -> MetaData:
    return array_metadata


@pytest.fixture
def seed_insert_statements(raw_arrays: RawRecordData) -> list[Insert]:
    return [insert(ArrayModel).values(raw_arrays)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.ArrayAsyncQuery
    pytest.skip(f"Date/Time tests can't be run on this dialect: {dialect}")


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.ArraySyncQuery
    pytest.skip(f"Date/Time tests can't be run on this dialect: {dialect}")


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
    raw_arrays: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    value_str = ", ".join(to_graphql_representation(v, "input") for v in value)
    query = f"""
        {{
            array(filter: {{ arrayStrCol: {{ {filter_name}: [{value_str}] }} }}) {{
                id
                arrayStrCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["array"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["array"][i]["id"] == raw_arrays[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
