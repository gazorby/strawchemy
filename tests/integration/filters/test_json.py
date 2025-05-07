from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy import Insert, MetaData, insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.models import JSONModel, json_metadata
from tests.integration.types import postgres as postgres_types
from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.fixture
def metadata() -> MetaData:
    return json_metadata


@pytest.fixture
def seed_insert_statements(raw_json: RawRecordData) -> list[Insert]:
    return [insert(JSONModel).values(raw_json)]


@pytest.fixture
def async_query(dialect: str) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.JSONAsyncQuery
    pytest.skip(f"JSON tests can't be run on this dialect: {dialect}")


@pytest.fixture
def sync_query(dialect: str) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.JSONSyncQuery
    pytest.skip(f"JSON tests can't be run on this dialect: {dialect}")


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
    raw_json: RawRecordData,
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
            json(filter: {{ dictCol: {{ {filter_name}: {value_repr} }} }}) {{
                id
                dictCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["json"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["json"][i]["id"] == raw_json[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
