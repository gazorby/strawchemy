from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from sqlalchemy import Executable, Insert, MetaData, insert, text
from tests.integration.models import HStoreModel, hstore_metadata
from tests.integration.types import postgres as postgres_types
from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor


@pytest.fixture
def before_create_all_statements() -> list[Executable]:
    return [text("CREATE EXTENSION IF NOT EXISTS hstore")]


@pytest.fixture
def metadata() -> MetaData:
    return hstore_metadata


@pytest.fixture
def seed_insert_statements(raw_hstore: RawRecordData) -> list[Insert]:
    return [insert(HStoreModel).values(raw_hstore)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.HStoreAsyncQuery
    pytest.skip(f"HStore tests can only be run on postgresql, not {dialect}")


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.HStoreSyncQuery
    pytest.skip(f"HStore tests can only be run on postgresql, not {dialect}")


@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("contains", {"key1": "value1"}, [0], id="contains"),
        pytest.param(
            "containedIn",
            {"key1": "value1", "key2": "value2", "key3": "value3", "extra": "value"},
            [0, 2],
            id="containedIn",
        ),
        pytest.param("hasKey", "key1", [0], id="hasKey"),
        pytest.param("hasKeyAll", ["key1", "key2"], [0], id="hasKeyAll"),
        pytest.param("hasKeyAny", ["key1", "status"], [0, 1], id="hasKeyAny"),
    ],
)
@pytest.mark.snapshot
async def test_hstore_filters(
    filter_name: str,
    value: Any,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_hstore: RawRecordData,
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
            hstore(filter: {{ hstoreCol: {{ {filter_name}: {value_repr} }} }}) {{
                id
                hstoreCol
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["hstore"]) == len(expected_ids)

    for i, expected_id in enumerate(expected_ids):
        assert result.data["hstore"][i]["id"] == raw_hstore[expected_id]["id"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_hstore_output(
    any_query: AnyQueryExecutor,
    raw_hstore: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            hstore {
                id
                hstoreCol
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    for hstore in result.data["hstore"]:
        expected = next(f for f in raw_hstore if f["id"] == hstore["id"])
        assert hstore["hstoreCol"] == expected["hstore_col"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
