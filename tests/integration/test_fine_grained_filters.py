from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from strawchemy import TextComparison
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SelectOf, SupportedDialect
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Green"}]
# Sweetness 5 (Strawberry) sits on the `sweeterThan: 5` boundary and 4 (Apple) just under it. Apple is only reachable
# through its name under `_or`. Red sums to 13, Yellow to exactly 10 (the `sum >= 10` boundary) and Green to 5; Red and
# Yellow hold two fruits, Green one.
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 8, "water_percent": 0.88, "color_id": 2},
    {"id": 5, "name": "Strawberry", "sweetness": 5, "water_percent": 0.91, "color_id": 3},
]


def _fruit_sweeter_than(statement: SelectOf[Fruit], value: int, **_ctx: Any) -> SelectOf[Fruit]:
    return statement.where(Fruit.sweetness >= value)


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Color, include=["id"], scope="schema")
    class ColorType: ...

    @strawchemy.filter(Fruit, include=["id", "name", "sweetness"], name="FruitFineGrainedFilter")
    class FruitFineGrainedFilter:
        name: TextComparison = strawchemy.filter_field(ops=["eq", "like"])
        sweeter_than: int = strawchemy.filter_field(apply=_fruit_sweeter_than)
        sweeter_than_in: int = strawchemy.filter_field(apply=_fruit_sweeter_than, join="in")

    # `sweetness` is included so `sum`'s `arguments=["sweetness"]` stays within the decorator's scope.
    @strawchemy.aggregate_filter(
        Fruit, include=["id", "sweetness"], functions=["count", "sum"], name="FruitFineGrainedAggregateFilter"
    )
    class FruitFineGrainedAggregateFilter:
        count: int = strawchemy.filter_field(ops=["gt"])
        sum: float = strawchemy.filter_field(arguments=["sweetness"], ops=["gte"])

    # With `fruits` alone, the nested fruit filter builds a `FruitFarmCountFields` DTO without fields (warning).
    @strawchemy.filter(Color, include=["name", "fruits"], name="ColorFineGrainedFilter")
    class ColorFineGrainedFilter:
        # Annotations resolve against the class namespace, which is where a builder-local filter has to be bound.
        _fruit_aggregate_filter = FruitFineGrainedAggregateFilter
        fruits_aggregate: _fruit_aggregate_filter  # ty: ignore[invalid-type-form]

    @strawberry.type
    class Query:
        fruits_fine_grained: list[FruitType] = strawchemy.field(filter_input=FruitFineGrainedFilter)
        colors_fine_grained: list[ColorType] = strawchemy.field(filter_input=ColorFineGrainedFilter)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


@pytest.mark.snapshot
async def test_custom_apply_filter_sweeter_than(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    threshold = 5
    expected_ids = {fruit["id"] for fruit in _FRUITS if fruit["sweetness"] >= threshold}
    query = f"""
        {{
            fruitsFineGrained(filter: {{ sweeterThan: {threshold} }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_custom_apply_filter_in_strategy(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    threshold = 5
    expected_ids = {fruit["id"] for fruit in _FRUITS if fruit["sweetness"] >= threshold}
    query = f"""
        {{
            fruitsFineGrained(filter: {{ sweeterThanIn: {threshold} }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("field", [pytest.param("sweeterThan", id="exists"), pytest.param("sweeterThanIn", id="in")])
async def test_null_custom_apply_filter_is_ignored(field: str, any_async_query: AnyQueryExecutor) -> None:
    """Test that a custom apply filter set to null filters nothing."""
    result = await maybe_async(any_async_query(f"{{ fruitsFineGrained(filter: {{ {field}: null }}) {{ id }} }}"))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == {fruit["id"] for fruit in _FRUITS}


async def test_custom_apply_filter_under_or(any_async_query: AnyQueryExecutor) -> None:
    threshold = 8
    target_name = _FRUITS[0]["name"]
    expected_ids = {fruit["id"] for fruit in _FRUITS if fruit["sweetness"] >= threshold or fruit["name"] == target_name}
    query = f"""
        {{
            fruitsFineGrained(
                filter: {{
                    _or: [
                        {{ sweeterThan: {threshold} }}
                        {{ name: {{ eq: "{target_name}" }} }}
                    ]
                }}
            ) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids


@pytest.mark.snapshot
async def test_declared_aggregate_count_filter(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """A declared aggregate filter still filters by count against the database."""
    threshold = 1
    counts: dict[Any, int] = {}
    for fruit in _FRUITS:
        counts[fruit["color_id"]] = counts.get(fruit["color_id"], 0) + 1
    expected_ids = {color["id"] for color in _COLORS if counts.get(color["id"], 0) > threshold}

    query = f"""
        {{
            colorsFineGrained(filter: {{
                fruitsAggregate: {{ count: {{ arguments: [id], predicate: {{ gt: {threshold} }} }} }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["colorsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_declared_aggregate_sum_filter(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """A declared aggregate filter narrowed to sum(sweetness) filters against the database.

    `count` narrowing goes through the same code path as an unmarked column filter; `sum`
    narrowing takes a different path (`arguments_type`/`EnumBackend`) that was previously only
    exercised by rejection tests, never against real data.
    """
    threshold = 10
    sums: dict[Any, int] = {}
    for fruit in _FRUITS:
        sums[fruit["color_id"]] = sums.get(fruit["color_id"], 0) + fruit["sweetness"]
    expected_ids = {color["id"] for color in _COLORS if sums.get(color["id"], 0) >= threshold}
    # Both a matching and a non-matching color must exist, or the query and a broken filter
    # (e.g. one that ignores the predicate) would return the same rows.
    assert expected_ids
    assert expected_ids != {color["id"] for color in _COLORS}

    query = f"""
        {{
            colorsFineGrained(filter: {{
                fruitsAggregate: {{ sum: {{ arguments: [sweetness], predicate: {{ gte: {threshold} }} }} }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["colorsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot
