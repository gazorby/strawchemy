from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy import Insert, MetaData, insert
from syrupy.assertion import SnapshotAssertion
from tests.integration.models import JSONModel, json_metadata
from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.typing import SupportedDialect

    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor


@pytest.fixture
def metadata() -> MetaData:
    return json_metadata


@pytest.fixture
def seed_insert_statements(raw_json: RawRecordData) -> list[Insert]:
    return [insert(JSONModel).values(raw_json)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.JSONAsyncQuery
    if dialect == "mysql":
        return mysql_types.JSONAsyncQuery
    if dialect == "sqlite":
        return sqlite_types.JSONAsyncQuery
    pytest.skip(f"JSON tests can't be run on this dialect: {dialect}")


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.JSONSyncQuery
    if dialect == "mysql":
        return mysql_types.JSONSyncQuery
    if dialect == "sqlite":
        return sqlite_types.JSONSyncQuery
    pytest.skip(f"JSON tests can't be run on this dialect: {dialect}")


# Tests for JSON-specific filters
@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("contains", {"key1": "value1"}, [0], id="contains"),
        pytest.param(
            "containedIn",
            {"key1": "value1", "key2": 2, "key3": 3, "key4": None, "nested": {"inner": "value"}, "extra": "value"},
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
    db_features: DatabaseFeatures,
) -> None:
    if db_features.dialect == "sqlite" and filter_name in {"contains", "containedIn"}:
        pytest.skip(f"contains/containedIn not supported on {db_features.dialect}")
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


@pytest.mark.snapshot
async def test_json_output(
    any_query: AnyQueryExecutor,
    raw_json: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            json {
                id
                dictCol
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    for interval in result.data["json"]:
        expected_interval = next(f for f in raw_json if f["id"] == interval["id"])
        assert interval["dictCol"] == expected_interval["dict_col"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("$.key1", id="key1"),
        pytest.param("$.key3", id="key3"),
        pytest.param("$.key4", id="key4"),
        pytest.param("$.nested", id="nested"),
    ],
)
@pytest.mark.snapshot
async def test_json_extract_path(
    path: str,
    any_query: AnyQueryExecutor,
    raw_json: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
        {{
            json {{
                id
                dictCol(path: "{path}")
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    for json in result.data["json"]:
        expected_dict_col = next(f for f in raw_json if f["id"] == json["id"])
        assert json["dictCol"] == expected_dict_col["dict_col"].get(path.strip("$."), {})

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_json_extract_inner_path(
    any_query: AnyQueryExecutor, raw_json: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        {
            json {
                id
                dictCol(path: "$.nested.inner")
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    for json in result.data["json"]:
        expected_dict_col = next(f for f in raw_json if f["id"] == json["id"])
        assert json["dictCol"] == expected_dict_col["dict_col"].get("nested", {}).get("inner", {})

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
