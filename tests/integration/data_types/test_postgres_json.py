from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Insert, MetaData, insert, null

from tests.integration.models import PostgresJSONModel, postgres_json_metadata
from tests.integration.types import postgres as postgres_types
from tests.integration.utils import graphql_input
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_ROWS: RawRecordData = [
    {"id": 1, "dict_col": {"key1": "value1", "key2": 2, "nested": {"inner": "value"}, "key3": 3, "key4": None}},
    {"id": 2, "dict_col": {"status": "pending", "count": 0, "key3": 3, "key4": None}},
    {"id": 3, "dict_col": {"key3": 3, "key4": None}},
    {"id": 4, "dict_col": null()},
]


@pytest.fixture
def metadata() -> MetaData:
    return postgres_json_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(PostgresJSONModel).values(_ROWS)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.PostgresJSONAsyncQuery
    pytest.skip(f"PostgreSQL json tests can't be run on this dialect: {dialect}")


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.PostgresJSONSyncQuery
    pytest.skip(f"PostgreSQL json tests can't be run on this dialect: {dialect}")


@pytest.mark.parametrize(
    ("comparison", "expected_ids"),
    [
        pytest.param({"contains": {"key1": "value1"}}, [1], id="contains"),
        pytest.param({"containedIn": {"key1": "value1", "key3": 3, "key4": None, "extra": 1}}, [3], id="containedIn"),
        pytest.param({"hasKey": "key1"}, [1], id="hasKey"),
        pytest.param({"hasKeyAll": ["key1", "key2"]}, [1], id="hasKeyAll"),
        pytest.param({"hasKeyAny": ["key1", "status"]}, [1, 2], id="hasKeyAny"),
        pytest.param({"eq": {"key4": None, "key3": 3}}, [3], id="eq"),
        pytest.param({"neq": {"key4": None, "key3": 3}}, [1, 2], id="neq"),
        pytest.param({"in": [{"key3": 3, "key4": None}, {"count": 0}]}, [3], id="in"),
        pytest.param({"nin": [{"key3": 3, "key4": None}]}, [1, 2], id="nin"),
        pytest.param({"isNull": True}, [4], id="isNull"),
        pytest.param({"isNull": False}, [1, 2, 3], id="isNotNull"),
    ],
)
@pytest.mark.parametrize("negated", [pytest.param(False, id="plain"), pytest.param(True, id="not")])
@pytest.mark.snapshot
async def test_postgres_json_filters(
    comparison: dict[str, Any],
    expected_ids: list[int],
    negated: bool,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that JSON filters on a PostgreSQL ``json`` column compare it as ``jsonb``."""
    ((name, value),) = comparison.items()
    dto_filter = f"{{ dictCol: {{ {name}: {graphql_input(value)} }} }}"
    if negated:
        dto_filter = f"{{ _not: {dto_filter} }}"
        expected_ids = [row["id"] for row in _ROWS if row["id"] not in expected_ids]
    result = await maybe_async(any_query(f"{{ json(filter: {dto_filter}) {{ id }} }}"))
    assert not result.errors
    assert result.data
    assert sorted(row["id"] for row in result.data["json"]) == expected_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_postgres_json_extract_path(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query('{ json { id dictCol(path: "$.nested.inner") } }'))
    assert not result.errors
    assert result.data
    assert {row["id"]: row["dictCol"] for row in result.data["json"]} == {1: "value", 2: {}, 3: {}, 4: {}}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
