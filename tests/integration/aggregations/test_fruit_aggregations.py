from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Literal

import pytest
import strawberry
from sqlalchemy import Insert, insert
from typing_extensions import override

from strawchemy import QueryHook
from strawchemy.schema.pagination import DefaultOffsetPagination
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.integration.typing import RawRecordData
from tests.integration.utils import compute_aggregation, from_graphql_representation, python_type
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.util import AliasedClass
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler.hook import LoadType
    from strawchemy.typing import SelectOf, SupportedDialect

pytestmark = [pytest.mark.integration]

_CREATED_AT = datetime(2024, 1, 1, 12)  # noqa: DTZ001
_COLORS: RawRecordData = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Orange"},
    {"id": 4, "name": "Green"},
    {"id": 5, "name": "Pink"},
]
# Fruit counts per color are 2 (Red), 4 (Yellow), 2 (Orange), 1 (Green) and 2 (Pink): a `count > 1` filter drops Green
# and a count ordering differs from id order. No two fruits of a color tie on sweetness, so ordering by it is total.
# Red, the color of the per-color cases, takes its minimum sweetness, water percent and name from Apple but its
# minimum creation date and best time to pick from Cherry.
_FRUITS: RawRecordData = [
    {
        "id": 1,
        "created_at": _CREATED_AT + timedelta(seconds=2),
        "name": "Apple",
        "sweetness": 4,
        "water_percent": 0.84,
        "best_time_to_pick": time(hour=10, minute=30),
        "color_id": 1,
    },
    {
        "id": 2,
        "created_at": _CREATED_AT + timedelta(seconds=1),
        "name": "Cherry",
        "sweetness": 9,
        "water_percent": 0.93,
        "best_time_to_pick": time(hour=9),
        "color_id": 1,
    },
    {
        "id": 3,
        "created_at": _CREATED_AT + timedelta(seconds=3),
        "name": "Banana",
        "sweetness": 2,
        "water_percent": 0.75,
        "best_time_to_pick": time(hour=17, minute=15),
        "color_id": 2,
    },
    {
        "id": 4,
        "created_at": _CREATED_AT + timedelta(seconds=4),
        "name": "Lemon",
        "sweetness": 1,
        "water_percent": 0.88,
        "best_time_to_pick": time(hour=20),
        "color_id": 2,
    },
    {
        "id": 5,
        "created_at": _CREATED_AT + timedelta(seconds=5),
        "name": "Quince",
        "sweetness": 3,
        "water_percent": 0.81,
        "best_time_to_pick": time(hour=13),
        "color_id": 2,
    },
    {
        "id": 6,
        "created_at": _CREATED_AT + timedelta(seconds=6),
        "name": "Orange",
        "sweetness": 8,
        "water_percent": 0.86,
        "best_time_to_pick": time(hour=12, minute=12),
        "color_id": 3,
    },
    {
        "id": 7,
        "created_at": _CREATED_AT + timedelta(seconds=7),
        "name": "clementine",
        "sweetness": 14,
        "water_percent": 0.9,
        "best_time_to_pick": time(hour=0, minute=0),
        "color_id": 3,
    },
    {
        "id": 8,
        "created_at": _CREATED_AT + timedelta(seconds=8),
        "name": "Strawberry",
        "sweetness": 5,
        "water_percent": 0.91,
        "best_time_to_pick": time(hour=9),
        "color_id": 4,
    },
    {
        "id": 9,
        "created_at": _CREATED_AT + timedelta(seconds=9),
        "name": "Cantaloupe",
        "sweetness": 0,
        "water_percent": 0.51,
        "best_time_to_pick": time(hour=20, minute=45, second=15, microsecond=10),
        "color_id": 2,
    },
    {
        "id": 10,
        "created_at": _CREATED_AT + timedelta(seconds=10),
        "name": "Watermelon",
        "sweetness": 7,
        "water_percent": 0.92,
        "best_time_to_pick": time(hour=19, microsecond=55),
        "color_id": 5,
    },
    {
        "id": 11,
        "created_at": _CREATED_AT + timedelta(seconds=11),
        "name": "Pears",
        "sweetness": 11,
        "water_percent": 0.15,
        "best_time_to_pick": time(hour=2),
        "color_id": 5,
    },
]
# Apple and Cherry share a color, so holding a different number of farms each makes an
# aggregate over farms differ between two siblings of the same fruit collection.
_FRUIT_FARMS: RawRecordData = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Apple farm 3", "fruit_id": 1},
    {"id": 4, "name": "Cherry farm", "fruit_id": 2},
    {"id": 5, "name": "Cherry farm 2", "fruit_id": 2},
    {"id": 6, "name": "Banana farm", "fruit_id": 3},
    {"id": 7, "name": "Lemon farm", "fruit_id": 4},
    {"id": 8, "name": "Quince farm", "fruit_id": 5},
    {"id": 9, "name": "Orange farm", "fruit_id": 6},
    {"id": 10, "name": "clementine farm", "fruit_id": 7},
    {"id": 11, "name": "Strawberry farm", "fruit_id": 8},
    {"id": 12, "name": "Cantaloupe farm", "fruit_id": 9},
    {"id": 13, "name": "Watermelon farm", "fruit_id": 10},
    {"id": 14, "name": "Pears farm", "fruit_id": 11},
]


class _FruitOrderingHook(QueryHook[Fruit]):
    load: Sequence[LoadType] = [Fruit.water_percent]

    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.order_by(alias.water_percent.asc())


class _MultiFarmFruitHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.join(FruitFarm, FruitFarm.fruit_id == alias.id).where(FruitFarm.name.endswith(" 2"))


def _schema(strawchemy: Strawchemy) -> Operations:
    # Declared before the Color types so that their `fruits` ordering reuses `FruitOrderBy`.
    @strawchemy.filter(Fruit, include=["sweetness"])
    class FruitFilter: ...

    @strawchemy.order(Fruit, include=["sweetness", "color_id"])
    class FruitOrderBy: ...

    @strawchemy.distinct_on(Fruit, include=["color_id"])
    class FruitDistinctOn: ...

    @strawchemy.type(Fruit, include=["id", "sweetness", "water_percent", "color", "farms"], override=True)
    class FruitType: ...

    @strawchemy.type(Fruit, include=["id", "farms"], query_hook=_FruitOrderingHook())
    class OrderedFruitType: ...

    @strawchemy.aggregate(Fruit, include=["id", "sweetness", "water_percent", "color", "farms"])
    class FruitAggregationType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], order=["id", "fruits"], override=True)
    class ColorType: ...

    @strawchemy.type(Color, include=["id", "fruits"], paginate=["fruits"])
    class ColorTypeWithPagination: ...

    @strawchemy.type(Color, include=["id", "fruits"], distinct_on=["fruits"])
    class ColorTypeWithDistinctOn: ...

    @strawchemy.type(Color, include=["id", "fruits"])
    class ColorWithMultiFarmFruits:
        fruits: list[FruitType] = strawchemy.field(query_hook=_MultiFarmFruitHook())

    @strawchemy.type(Color, include=["id", "fruits"])
    class ColorWithOrderedFruits:
        fruits: list[OrderedFruitType]

    @strawchemy.filter(Color, include=["name", "fruits"])
    class ColorFilter: ...

    # `id` keeps the fruit count fields of `fruitsAggregate` from being empty.
    @strawchemy.order(Color, include=["id", "fruits"])
    class ColorOrder: ...

    @strawchemy.create_input(Color, include=["name"])
    class ColorCreateInput: ...

    @strawberry.type
    class Query:
        color: ColorType = strawchemy.field()
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter, order_by_input=ColorOrder)
        colors_paginated: list[ColorTypeWithPagination] = strawchemy.field(pagination=True)
        colors_nested_distinct: list[ColorTypeWithDistinctOn] = strawchemy.field()
        colors_with_multi_farm_fruits: list[ColorWithMultiFarmFruits] = strawchemy.field()
        colors_with_ordered_fruits: list[ColorWithOrderedFruits] = strawchemy.field()
        fruit_aggregations: FruitAggregationType = strawchemy.field(root_aggregations=True)
        fruit_aggregations_paginated_limit_2: FruitAggregationType = strawchemy.field(
            root_aggregations=True, pagination=DefaultOffsetPagination(limit=2)
        )
        fruit_aggregations_filterable: FruitAggregationType = strawchemy.field(
            root_aggregations=True,
            filter_input=FruitFilter,
            order_by_input=FruitOrderBy,
            distinct_on=FruitDistinctOn,
            pagination=True,
        )

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreateInput)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FRUIT_FARMS)]


@pytest.mark.snapshot
async def test_count_aggregation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the count aggregation function."""
    query = f"""
        {{
            color(id: {_COLORS[0]["id"]}) {{
                fruitsAggregate {{
                    count
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["color"]["fruitsAggregate"]["count"] == len(
        [fruit for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"]]
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_aggregation_without_related_rows(any_async_query: AnyQueryExecutor) -> None:
    """Test that a parent with no related rows is returned with a zero count and null extrema."""
    created = await maybe_async(any_async_query('mutation { createColor(data: { name: "Blue" }) { id } }'))
    assert not created.errors

    result = await maybe_async(
        any_async_query(
            """
            {
                colors(filter: { name: { eq: "Blue" } }) {
                    name
                    fruitsAggregate {
                        count
                        max { sweetness }
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["colors"] == [{"name": "Blue", "fruitsAggregate": {"count": 0, "max": {"sweetness": None}}}]


async def test_nested_aggregation_correlates_to_its_own_element(any_async_query: AnyQueryExecutor) -> None:
    """Test that an aggregate nested under a to-many relation reports the value of its own element."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    id
                    fruits {
                        id
                        farmsAggregate { max { id } }
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert [color["id"] for color in result.data["colors"]] == [color["id"] for color in _COLORS]
    actual = {
        fruit["id"]: fruit["farmsAggregate"]["max"]["id"]
        for color in result.data["colors"]
        for fruit in color["fruits"]
    }
    assert actual == {
        fruit["id"]: max(farm["id"] for farm in _FRUIT_FARMS if farm["fruit_id"] == fruit["id"]) for fruit in _FRUITS
    }


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation(
    field_name: str,
    raw_field_name: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the sum aggregation function for a specific field."""
    query = f"""
        {{
            color(id: {_COLORS[0]["id"]}) {{
                fruitsAggregate {{
                    sum {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    # Calculate expected value
    expected_sum = sum(fruit[raw_field_name] for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"])

    # Verify result
    actual_sum = result.data["color"]["fruitsAggregate"]["sum"][field_name]

    assert pytest.approx(actual_sum) == expected_sum

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("name", "name"),
        ("createdAt", "created_at"),
        ("bestTimeToPick", "best_time_to_pick"),
    ],
)
@pytest.mark.snapshot
async def test_min_aggregation(
    field_name: str,
    raw_field_name: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the min aggregation function for a specific field."""
    query = f"""
        {{
            color(id: {_COLORS[0]["id"]}) {{
                fruitsAggregate {{
                    min {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    # Verify result
    actual_min = from_graphql_representation(
        result.data["color"]["fruitsAggregate"]["min"][field_name], python_type(Fruit, raw_field_name)
    )
    assert actual_min is not None

    # For fields where we can calculate expected values, verify them
    expected_min = min(fruit[raw_field_name] for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"])

    assert actual_min == expected_min

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
        ("name", "name"),
        ("createdAt", "created_at"),
        ("bestTimeToPick", "best_time_to_pick"),
    ],
)
@pytest.mark.snapshot
async def test_max_aggregation(
    field_name: str,
    raw_field_name: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the max aggregation function for a specific field."""
    query = f"""
        {{
            color(id: {_COLORS[0]["id"]}) {{
                fruitsAggregate {{
                    max {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    # Verify result
    actual_max = from_graphql_representation(
        result.data["color"]["fruitsAggregate"]["max"][field_name], python_type(Fruit, raw_field_name)
    )
    assert actual_max is not None

    # For fields where we can calculate expected values, verify them
    expected_max = max(fruit[raw_field_name] for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"])

    assert actual_max == expected_max

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "agg_type",
    ["avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
)
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
    ],
)
@pytest.mark.snapshot
async def test_statistical_aggregation(
    agg_type: Literal["avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    db_features: DatabaseFeatures,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    if agg_type not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {agg_type} aggregation function")

    query = f"""
        {{
            color(id: {_COLORS[0]["id"]}) {{
                fruitsAggregate {{
                    {agg_type} {{
                        {field_name}
                    }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    # Verify result is a number or null
    actual_value = from_graphql_representation(
        result.data["color"]["fruitsAggregate"][agg_type][field_name], python_type(Fruit, raw_field_name)
    )

    expected_value = compute_aggregation(
        agg_type, [fruit[raw_field_name] for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"]]
    )

    assert pytest.approx(actual_value) == expected_value

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "pagination",
    [pytest.param(None, id="no-pagination"), pytest.param(DefaultOffsetPagination(limit=2), id="pagination")],
)
@pytest.mark.parametrize("agg_type", ["sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"])
@pytest.mark.parametrize(
    ("field_name", "raw_field_name"),
    [
        ("sweetness", "sweetness"),
        ("waterPercent", "water_percent"),
    ],
)
@pytest.mark.snapshot
async def test_root_aggregation(
    agg_type: Literal["sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
    field_name: str,
    raw_field_name: str,
    pagination: DefaultOffsetPagination | None,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    db_features: DatabaseFeatures,
) -> None:
    """Test statistical aggregation functions for a specific field."""
    if agg_type not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {agg_type} aggregation function")

    query_name = "fruitAggregations" if pagination is None else "fruitAggregationsPaginatedLimit2"
    query = f"""
        {{
            {query_name} {{
                aggregations {{
                    {agg_type} {{
                        {field_name}
                    }}
                }}
                nodes {{
                    id
                    {field_name}
                }}
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    # Verify result is a number or null
    actual_value = from_graphql_representation(
        result.data[query_name]["aggregations"][agg_type][field_name], python_type(Fruit, raw_field_name)
    )
    if pagination is None:
        expected_value = compute_aggregation(agg_type, [record[raw_field_name] for record in _FRUITS])
    else:
        expected_value = compute_aggregation(
            agg_type, [record[raw_field_name] for record in _FRUITS[: pagination.limit]]
        )

    rel = (
        0.0001 if db_features.dialect == "mysql" and field_name == "sweetness" and agg_type in ("avg", "sum") else None
    )
    assert actual_value == pytest.approx(expected_value, rel=rel)

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def _data(any_async_query: AnyQueryExecutor, query: str) -> dict[str, Any]:
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    return result.data


def _farms_aggregate(fruit_id: int) -> dict[str, Any]:
    names = [farm["name"] for farm in _FRUIT_FARMS if farm["fruit_id"] == fruit_id]
    return {"count": len(names), "min": {"name": min(names)}, "max": {"name": max(names)}}


@pytest.mark.parametrize(
    ("root", "arguments"),
    [
        pytest.param("colors", "(orderBy: { sweetness: ASC })", id="order-by"),
        pytest.param("colorsPaginated", "(limit: 10, offset: 0)", id="limit-offset"),
        pytest.param("colorsPaginated", "", id="default-pagination"),
    ],
)
async def test_nested_aggregation_under_relation_with_arguments(
    root: str,
    arguments: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that an aggregate under a relation that gets its own subquery is computed per related row."""
    data = await _data(
        any_async_query,
        f"""
        {{
            {root} {{
                id
                fruits{arguments} {{ id farmsAggregate {{ count min {{ name }} max {{ name }} }} }}
            }}
        }}
        """,
    )
    fruits = [fruit for color in data[root] for fruit in color["fruits"]]
    assert sorted(fruit["id"] for fruit in fruits) == sorted(
        fruit["id"] for fruit in _FRUITS if fruit["color_id"] is not None
    )
    for fruit in fruits:
        assert fruit["farmsAggregate"] == _farms_aggregate(fruit["id"])
    assert query_tracker.query_count == 1


async def test_nested_aggregation_under_relation_with_distinct_on(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that an aggregate under a relation with DISTINCT ON is computed per kept row."""
    data = await _data(
        any_async_query,
        """
        {
            colorsNestedDistinct {
                id
                fruits(distinctOn: [sweetness]) { id sweetness farmsAggregate { count min { name } max { name } } }
            }
        }
        """,
    )
    for color in data["colorsNestedDistinct"]:
        sweetness = {fruit["sweetness"] for fruit in _FRUITS if fruit["color_id"] == color["id"]}
        assert sorted(fruit["sweetness"] for fruit in color["fruits"]) == sorted(sweetness)
        for fruit in color["fruits"]:
            assert fruit["farmsAggregate"] == _farms_aggregate(fruit["id"])
    assert query_tracker.query_count == 1


_ROOT_AGGREGATION_NEXT_TO_NESTED = """
    {{
        colors{arguments} {{
            id
            fruitsAggregate {{ count }}
            fruits(orderBy: {{ sweetness: ASC }}) {{ id farmsAggregate {{ count }} }}
        }}
    }}
"""


def _assert_nested_aggregates(colors: list[dict[str, Any]]) -> None:
    fruit_counts = Counter(fruit["color_id"] for fruit in _FRUITS)
    for color in colors:
        fruits = sorted(
            (fruit for fruit in _FRUITS if fruit["color_id"] == color["id"]), key=lambda fruit: fruit["sweetness"]
        )
        assert color["fruitsAggregate"] == {"count": fruit_counts[color["id"]]}
        assert color["fruits"] == [
            {"id": fruit["id"], "farmsAggregate": {"count": _farms_aggregate(fruit["id"])["count"]}} for fruit in fruits
        ]


async def test_root_aggregation_filter_next_to_nested_aggregation(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test a root aggregation filter next to an aggregate under an ordered relation."""
    data = await _data(
        any_async_query,
        _ROOT_AGGREGATION_NEXT_TO_NESTED.format(
            arguments="(filter: { fruitsAggregate: { count: { predicate: { gt: 1 } } } })"
        ),
    )
    fruit_counts = Counter(fruit["color_id"] for fruit in _FRUITS)
    assert {color["id"] for color in data["colors"]} == {
        color_id for color_id, count in fruit_counts.items() if count > 1
    }
    _assert_nested_aggregates(data["colors"])
    assert query_tracker.query_count == 1


async def test_root_aggregation_order_by_next_to_nested_aggregation(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test a root aggregation ordering next to an aggregate under an ordered relation."""
    data = await _data(
        any_async_query,
        _ROOT_AGGREGATION_NEXT_TO_NESTED.format(arguments="(orderBy: { fruitsAggregate: { count: DESC } })"),
    )
    counts = [color["fruitsAggregate"]["count"] for color in data["colors"]]
    assert counts == sorted(counts, reverse=True)
    _assert_nested_aggregates(data["colors"])
    assert query_tracker.query_count == 1


@pytest.mark.parametrize(
    ("root", "expected_fruit_ids"),
    [
        pytest.param("colorsWithOrderedFruits", None, id="ordering-hook"),
        pytest.param("colorsWithMultiFarmFruits", {1, 2}, id="joining-hook"),
    ],
)
async def test_nested_aggregation_under_hooked_relation(
    root: str,
    expected_fruit_ids: set[int] | None,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that an aggregate under a relation whose query hook is not WHERE-only is computed per related row."""
    data = await _data(any_async_query, f"{{ {root} {{ id fruits {{ id farmsAggregate {{ count }} }} }} }}")
    fruits = [fruit for color in data[root] for fruit in color["fruits"]]
    colored_fruit_ids = {fruit["id"] for fruit in _FRUITS if fruit["color_id"] is not None}
    assert {fruit["id"] for fruit in fruits} == (expected_fruit_ids or colored_fruit_ids)
    for fruit in fruits:
        assert fruit["farmsAggregate"] == {"count": _farms_aggregate(fruit["id"])["count"]}
    assert query_tracker.query_count == 1


async def test_aggregation_two_levels_under_relation_with_arguments(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that an aggregate under a to-one relation of an ordered relation reports its own parent's value."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    id
                    fruits(orderBy: { sweetness: ASC }) {
                        id
                        color {
                            id
                            fruitsAggregate { count sum { sweetness } min { sweetness } max { sweetness } }
                        }
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    for color in result.data["colors"]:
        sweetness = [fruit["sweetness"] for fruit in _FRUITS if fruit["color_id"] == color["id"]]
        expected = {
            "count": len(sweetness),
            "sum": {"sweetness": sum(sweetness)},
            "min": {"sweetness": min(sweetness)},
            "max": {"sweetness": max(sweetness)},
        }
        assert [fruit["color"] for fruit in color["fruits"]] == [
            {"id": color["id"], "fruitsAggregate": expected} for _ in sweetness
        ]
    assert query_tracker.query_count == 1


@pytest.mark.allow_duplicate_reads(
    reason=(
        "on postgresql, colors and colors.fruits.color each compute fruitsAggregate in a LATERAL correlated to "
        "their own alias; the CTE databases share one grouped CTE"
    ),
    dialects=("postgresql",),
)
async def test_same_aggregate_on_root_and_under_relation(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that one aggregate selected on the root and under a relation reports each parent's value."""
    result = await maybe_async(
        any_async_query(
            "{ colors { id fruitsAggregate { count } fruits { id color { id fruitsAggregate { count } } } } }"
        )
    )
    assert not result.errors
    assert result.data
    for color in result.data["colors"]:
        count = sum(1 for fruit in _FRUITS if fruit["color_id"] == color["id"])
        assert color["fruitsAggregate"] == {"count": count}
        assert [fruit["color"] for fruit in color["fruits"]] == [
            {"id": color["id"], "fruitsAggregate": {"count": count}} for _ in range(count)
        ]
    assert query_tracker.query_count == 1


async def test_aggregate_under_aliases_differing_in_limit(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    db_features: DatabaseFeatures,
) -> None:
    """Test that aliases of a relation differing in limit each count their farms, sharing one grouped CTE without LATERAL."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colorsPaginated {
                    id
                    a: fruits(limit: 1) { id farmsAggregate { count } }
                    b: fruits(limit: 2) { id farmsAggregate { count } }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    farm_counts = Counter(farm["fruit_id"] for farm in _FRUIT_FARMS)
    for color in result.data["colorsPaginated"]:
        fruits = [
            {"id": fruit["id"], "farmsAggregate": {"count": farm_counts[fruit["id"]]}}
            for fruit in sorted(_FRUITS, key=lambda fruit: fruit["id"])
            if fruit["color_id"] == color["id"]
        ]
        assert color["a"] == fruits[:1]
        assert color["b"] == fruits[:2]
    assert query_tracker.query_count == 1
    if not db_features.supports_lateral:
        assert len(re.findall(r"\banon_\d+ AS\s*\(", query_tracker[0].statement_str)) == 2


async def test_nested_aggregation_under_aliased_relations_with_arguments(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that each alias of an ordered relation computes its own nested aggregate."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    id
                    a: fruits(orderBy: { sweetness: ASC }) { id farmsAggregate { count min { name } max { name } } }
                    b: fruits(orderBy: { sweetness: DESC }) { id farmsAggregate { count } }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    for color in result.data["colors"]:
        fruits = sorted(
            (fruit for fruit in _FRUITS if fruit["color_id"] == color["id"]), key=lambda fruit: fruit["sweetness"]
        )
        assert color["a"] == [{"id": fruit["id"], "farmsAggregate": _farms_aggregate(fruit["id"])} for fruit in fruits]
        assert color["b"] == [
            {"id": fruit["id"], "farmsAggregate": {"count": _farms_aggregate(fruit["id"])["count"]}}
            for fruit in reversed(fruits)
        ]
    assert query_tracker.query_count == 1


_ROOT_AGGREGATION_FUNCTIONS: dict[
    Literal["sum", "avg", "min", "max", "stddevSamp", "stddevPop", "varSamp", "varPop"], str
] = {
    "sum": "sum",
    "avg": "avg",
    "min": "min",
    "max": "max",
    "stddevSamp": "stddev_samp",
    "stddevPop": "stddev_pop",
    "varSamp": "var_samp",
    "varPop": "var_pop",
}


@pytest.mark.parametrize(
    "relations",
    [
        pytest.param("farms { name }", id="to-many"),
        pytest.param("color { fruits { id } }", id="to-many-under-to-one"),
        pytest.param("color { fruits { id farms { name } } }", id="to-many-two-levels"),
        pytest.param("farms { name } color { fruits { id } }", id="to-many-siblings"),
        pytest.param("color { fruits(orderBy: { sweetness: ASC }) { id } }", id="to-many-with-arguments"),
        pytest.param(
            "color { a: fruits(orderBy: { sweetness: ASC }) { id } b: fruits(orderBy: { sweetness: DESC }) { id } }",
            id="to-many-aliases",
        ),
    ],
)
@pytest.mark.parametrize(
    ("root", "expected_ids"),
    [
        pytest.param("fruitAggregations", set(range(1, 12)), id="all"),
        pytest.param("fruitAggregationsPaginatedLimit2", {1, 2}, id="default-limit"),
        pytest.param(
            "fruitAggregationsFilterable(filter: { sweetness: { gt: 4 } })", {2, 6, 7, 8, 10, 11}, id="filter"
        ),
        pytest.param(
            "fruitAggregationsFilterable(orderBy: { sweetness: DESC }, limit: 3, offset: 1)", {2, 6, 11}, id="paginated"
        ),
        pytest.param(
            "fruitAggregationsFilterable(distinctOn: [colorId], orderBy: [{ colorId: ASC }, { sweetness: DESC }])",
            {2, 5, 7, 8, 11},
            id="distinct-on",
        ),
    ],
)
async def test_root_aggregation_next_to_to_many_relations(
    root: str,
    expected_ids: set[int],
    relations: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    db_features: DatabaseFeatures,
) -> None:
    """Test that root aggregations selected next to to-many relations aggregate each root row once."""
    functions = [
        name for name, sql_name in _ROOT_AGGREGATION_FUNCTIONS.items() if sql_name in db_features.aggregation_functions
    ]
    selections = " ".join(f"{name} {{ sweetness }}" for name in functions)
    data = await _data(
        any_async_query, f"{{ {root} {{ aggregations {{ count {selections} }} nodes {{ id {relations} }} }} }}"
    )
    result = data[root.split("(", maxsplit=1)[0]]
    assert {node["id"] for node in result["nodes"]} == expected_ids
    sweetness = [fruit["sweetness"] for fruit in _FRUITS if fruit["id"] in expected_ids]
    assert result["aggregations"]["count"] == len(expected_ids)
    rel = 0.0001 if db_features.dialect == "mysql" else None
    for name in functions:
        expected = pytest.approx(compute_aggregation(name, sweetness), rel=rel)
        assert result["aggregations"][name]["sweetness"] == expected, name
    assert query_tracker.query_count == 1
