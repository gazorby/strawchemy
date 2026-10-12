from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, MetaData, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import ArrayModel, array_metadata
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


_ARRAYS: RawRecordData = [
    {"id": 1, "array_str_col": ["one", "two", "three"]},
    {"id": 2, "array_str_col": ["apple", "banana", "cherry", "date"]},
    {"id": 3, "array_str_col": []},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.filter(ArrayModel, include=["array_str_col"])
    class ArrayFilter: ...

    @strawchemy.type(ArrayModel, include=["id", "array_str_col"])
    class ArrayType: ...

    @strawberry.type
    class Query:
        array: list[ArrayType] = strawchemy.field(filter_input=ArrayFilter)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    if dialect != "postgresql":
        pytest.skip(f"Array tests can't be run on this dialect: {dialect}")
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture(name="metadata")
def fx_metadata() -> MetaData:
    return array_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(ArrayModel).values(_ARRAYS)]


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
    any_async_query: AnyQueryExecutor,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["array"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["array"][i]["id"] == _ARRAYS[expected_id]["id"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("filter_name", "expected_ids"),
    [
        pytest.param("contains", [1, 2, 3], id="contains"),
        pytest.param("containedIn", [3], id="containedIn"),
        pytest.param("overlap", [], id="overlap"),
        pytest.param("in", [], id="in"),
        pytest.param("nin", [1, 2, 3], id="nin"),
    ],
)
async def test_postgres_array_filters_empty_list(
    filter_name: str, expected_ids: list[int], any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(
        any_async_query(f"{{ array(filter: {{ arrayStrCol: {{ {filter_name}: [] }} }}) {{ id }} }}")
    )
    assert not result.errors
    assert result.data is not None
    assert sorted(row["id"] for row in result.data["array"]) == expected_ids


@pytest.mark.parametrize("operator", ["contains", "containedIn", "overlap"])
@pytest.mark.parametrize("negated", [pytest.param(False, id="plain"), pytest.param(True, id="not")])
async def test_postgres_array_null_operator_is_ignored(
    operator: str, negated: bool, any_async_query: AnyQueryExecutor
) -> None:
    """Test that an array operator set to null is ignored, directly and under ``_not``."""
    dto_filter = f"{{ arrayStrCol: {{ {operator}: null }} }}"
    if negated:
        dto_filter = f"{{ _not: {dto_filter} }}"
    result = await maybe_async(any_async_query(f"{{ array(filter: {dto_filter}) {{ id }} }}"))
    assert not result.errors
    assert result.data is not None
    assert sorted(row["id"] for row in result.data["array"]) == sorted(row["id"] for row in _ARRAYS)
