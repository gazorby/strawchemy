from __future__ import annotations

from typing import Literal
from uuid import uuid4

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import Insert, insert
from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .models import Color, Fruit, SQLDataTypes, SQLDataTypesContainer
from .types import (
    FruitOrderBy,
    FruitType,
    SQLDataTypesContainerOrderBy,
    SQLDataTypesContainerType,
    SQLDataTypesOrderBy,
    SQLDataTypesType,
    strawchemy,
)
from .typing import RawRecordData
from .utils import compute_aggregation

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitType] = strawchemy.field(order_by=FruitOrderBy, repository_type=StrawchemyAsyncRepository)
    data_types: list[SQLDataTypesType] = strawchemy.field(
        order_by=SQLDataTypesOrderBy, repository_type=StrawchemyAsyncRepository
    )
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository, order_by=SQLDataTypesContainerOrderBy
    )


@strawberry.type
class SyncQuery:
    fruits: list[FruitType] = strawchemy.field(order_by=FruitOrderBy, repository_type=StrawchemySyncRepository)
    data_types: list[SQLDataTypesType] = strawchemy.field(
        order_by=SQLDataTypesOrderBy, repository_type=StrawchemySyncRepository
    )
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        repository_type=StrawchemySyncRepository, order_by=SQLDataTypesContainerOrderBy
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.fixture
def raw_containers() -> RawRecordData:
    return [{"id": str(uuid4())}, {"id": str(uuid4())}]


@pytest.fixture
def seed_insert_statements(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    raw_containers: RawRecordData,
    raw_sql_data_types_set1: RawRecordData,
    raw_sql_data_types_set2: RawRecordData,
) -> list[Insert]:
    return [
        insert(Color).values(raw_colors),
        insert(Fruit).values(raw_fruits),
        insert(SQLDataTypesContainer).values(raw_containers),
        insert(SQLDataTypes).values(raw_sql_data_types_set1),
        insert(SQLDataTypes).values(raw_sql_data_types_set2),
    ]


@pytest.fixture
def raw_sql_data_types_set12(
    raw_sql_data_types_set1: RawRecordData, raw_sql_data_types_set2: RawRecordData
) -> RawRecordData:
    return raw_sql_data_types_set1 + raw_sql_data_types_set2


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by(
    order_by: Literal["ASC", "DESC"],
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(f"{{ fruits(orderBy: {{ name: {order_by} }}) {{ id name }} }}"))
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [{"id": row["id"], "name": row["name"]} for row in raw_fruits]
    expected_sort = sorted(expected_sort, key=lambda x: x["name"], reverse=order_by == "DESC")
    assert [{"id": row["id"], "name": row["name"]} for row in result.data["fruits"]] == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"])
@pytest.mark.snapshot
async def test_nulls(
    order_by: Literal["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"],
    any_query: AnyQueryExecutor,
    raw_sql_data_types_set12: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_query(f"{{ dataTypes(orderBy: {{ optionalStrCol: {order_by} }}) {{ id optionalStrCol }} }}")
    )
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [
        {"id": row["id"], "optionalStrCol": row["optional_str_col"]}
        for row in raw_sql_data_types_set12
        if row["optional_str_col"] is not None
    ]
    nulls = [
        {"id": row["id"], "optionalStrCol": row["optional_str_col"]}
        for row in raw_sql_data_types_set12
        if row["optional_str_col"] is None
    ]
    expected_sort = sorted(expected_sort, key=lambda x: x["optionalStrCol"], reverse=order_by.startswith("DESC"))
    expected_sort = expected_sort + nulls if order_by.endswith("LAST") else nulls + expected_sort
    actual_sort = [{"id": row["id"], "optionalStrCol": row["optionalStrCol"]} for row in result.data["dataTypes"]]
    assert actual_sort == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "aggregation",
    ["max", "min", "sum", "avg", "stddev", "stddevSamp", "stddevPop", "variance", "varSamp", "varPop"],
)
@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by_aggregations(
    order_by: Literal["ASC", "DESC"],
    aggregation: Literal[
        "max", "min", "sum", "avg", "variance", "stddev", "varPop", "stddevPop", "varSamp", "stddevSamp"
    ],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_containers: RawRecordData,
    raw_sql_data_types_set1: RawRecordData,
    raw_sql_data_types_set2: RawRecordData,
) -> None:
    result = await maybe_async(
        any_query(
            f"""{{
            containers(orderBy: {{ dataTypesAggregate: {{ {aggregation}: {{ intCol: {order_by} }} }} }}) {{
                id
                dataTypes {{
                    intCol
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    container1_id = raw_containers[0]["id"]
    container2_id = raw_containers[1]["id"]
    set1_values = [x["int_col"] for x in raw_sql_data_types_set1]
    set2_values = [x["int_col"] for x in raw_sql_data_types_set2]

    expected_order = (
        [container1_id, container2_id]
        if compute_aggregation(aggregation, set1_values) <= compute_aggregation(aggregation, set2_values)
        else [container2_id, container1_id]
    )
    if order_by == "DESC":
        expected_order.reverse()

    assert [row["id"] for row in result.data["containers"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_relation_order_by(
    order_by: Literal["ASC", "DESC"],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_containers: RawRecordData,
    raw_sql_data_types_set1: RawRecordData,
    raw_sql_data_types_set2: RawRecordData,
) -> None:
    result = await maybe_async(
        any_query(
            f"""{{
            containers {{
                id
                dataTypes(orderBy: {{ intCol: {order_by} }}) {{
                    intCol
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    for container in result.data["containers"]:
        raw_data_types = (
            raw_sql_data_types_set1 if container["id"] == raw_containers[0]["id"] else raw_sql_data_types_set2
        )
        expected_order = sorted([x["int_col"] for x in raw_data_types], reverse=order_by == "DESC")
        assert [row["intCol"] for row in container["dataTypes"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
