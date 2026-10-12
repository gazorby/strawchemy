from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Fruit counts per color are 2 (Red), 3 (Yellow), 2 (Orange), 1 (Green) and 2 (Pink), so count predicates keep rows on
# both sides of every threshold. Fruit aggregates per color:
#
#   color   sweetness sum / avg   water percent sum / avg    min / max name
#   Red     13 / 6.5              1.77 / 0.885               Apple / Cherry
#   Yellow  6 / 2                 2.44 / 0.8133              Banana / Quince
#   Orange  22 / 11               1.76 / 0.88                Orange or clementine (collation)
#   Green   5 / 5                 0.91 / 0.91                Strawberry
#   Pink    18 / 9                1.07 / 0.535               Pears / Watermelon
#
# Green sums to exactly 5, the boundary of the paginated `sum > 5` filter.
_COLORS: list[dict[str, Any]] = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Orange"},
    {"id": 4, "name": "Green"},
    {"id": 5, "name": "Pink"},
]
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 1, "water_percent": 0.88, "color_id": 2},
    {"id": 5, "name": "Quince", "sweetness": 3, "water_percent": 0.81, "color_id": 2},
    {"id": 6, "name": "Orange", "sweetness": 8, "water_percent": 0.86, "color_id": 3},
    {"id": 7, "name": "clementine", "sweetness": 14, "water_percent": 0.9, "color_id": 3},
    {"id": 8, "name": "Strawberry", "sweetness": 5, "water_percent": 0.91, "color_id": 4},
    {"id": 9, "name": "Watermelon", "sweetness": 7, "water_percent": 0.92, "color_id": 5},
    {"id": 10, "name": "Pears", "sweetness": 11, "water_percent": 0.15, "color_id": 5},
]
# Apple and Cherry hold more than one farm, the other fruits exactly one, so a farm count filter splits the fruits.
_FRUIT_FARMS: list[dict[str, Any]] = [
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
    {"id": 12, "name": "Watermelon farm", "fruit_id": 9},
    {"id": 13, "name": "Pears farm", "fruit_id": 10},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "color"], override=True)
    class FruitType: ...

    # The order list also filters the order inputs of `fruits`: `sweetness` is the column the sum orders by.
    @strawchemy.type(
        Color, include=["id", "name", "fruits"], order=["id", "name", "sweetness", "fruits"], override=True
    )
    class ColorType: ...

    # The include list also filters the columns `fruitsAggregate` predicates take as arguments.
    @strawchemy.filter(Fruit, include=["id", "name", "sweetness", "water_percent", "color", "farms"])
    class FruitFilter: ...

    @strawchemy.filter(Color, include=["name", "fruits"])
    class ColorFilter: ...

    @strawchemy.order(Color, include=["name", "fruits"])
    class ColorOrder: ...

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field(filter_input=FruitFilter)
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter, order_by_input=ColorOrder)
        colors_filterable_paginated: list[ColorType] = strawchemy.field(
            filter_input=ColorFilter, order_by_input=ColorOrder, pagination=True
        )

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FRUIT_FARMS)]


@pytest.mark.parametrize(
    ("predicate", "value", "expected_indices"),
    [
        pytest.param("eq", 2, [0, 2, 4], id="eq-match"),
        pytest.param("neq", 3, [0, 2, 3, 4], id="neq-match"),
        pytest.param("gt", 1, [0, 1, 2, 4], id="gt-match"),
        pytest.param("gte", 2, [0, 1, 2, 4], id="gte-match"),
        pytest.param("lt", 3, [0, 2, 3, 4], id="lt-match"),
        pytest.param("lte", 2, [0, 2, 3, 4], id="lte-match"),
        pytest.param("in", [1, 3], [1, 3], id="in-match"),
        pytest.param("nin", [0, 3, 4], [0, 2, 3, 4], id="nin-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter(
    predicate: str,
    value: int | list[int],
    expected_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation."""
    # Prepare the value for GraphQL query
    value_str = f"[{', '.join(str(v) for v in value)}]" if isinstance(value, list) else str(value)

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    count: {{
                        arguments: [id]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["colors"]}

    # Get the expected container IDs
    expected_container_ids = {_COLORS[idx]["id"] for idx in expected_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("name", "eq", "Apple", [0], id="eq-match"),
        pytest.param("name", "like", "%pp%", [0], id="like-match"),
        pytest.param("name", "ilike", "%APP%", [0], id="ilike-match"),
        pytest.param("name", "startswith", "App", [0], id="startswith-match"),
        pytest.param("name", "contains", "ppl", [0], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_min_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_color_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by minString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    minString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {_COLORS[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("name", "eq", "Cherry", [0], id="eq-match"),
        pytest.param("name", "like", "%err%", [0, 3], id="like-match"),
        pytest.param("name", "ilike", "%ERR%", [0, 3], id="ilike-match"),
        pytest.param("name", "startswith", "Che", [0], id="startswith-match"),
        pytest.param("name", "contains", "err", [0, 3], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_max_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_color_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by maxString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    maxString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {_COLORS[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("sweetness", "eq", 6, [1], id="int-eq-match"),
        pytest.param("sweetness", "gt", 8, [0, 2, 4], id="int-gt-match"),
        pytest.param("waterPercent", "eq", 1.77, [0], id="float-eq-match"),
        pytest.param("waterPercent", "gt", 1.7, [0, 1, 2], id="float-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_color_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by sum aggregation."""
    value_str = str(value)

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    sum: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {_COLORS[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("sweetness", "eq", 6.5, [0], id="int-avg-eq-match"),
        pytest.param("sweetness", "gt", 7.0, [2, 4], id="int-avg-gt-match"),
        pytest.param("waterPercent", "eq", 0.885, [0], id="float-avg-eq-match"),
        pytest.param("waterPercent", "gt", 0.85, [0, 2, 3], id="float-avg-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_avg_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_color_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by avg aggregation."""
    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    avg: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {_COLORS[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_count_aggregation_filter_nested_under_or(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that an aggregation predicate nested under a top-level ``_or`` is discovered and applied.

    Guards the build-once collect pass: it must walk into ``_or``/``_not`` branches when
    gathering aggregation filters, otherwise the nested predicate is silently dropped. The
    snapshot shows the aggregation subquery is emitted under the ``OR`` branch.
    """
    query = """
        {
            colors(filter: {
                _or: [
                    { fruitsAggregate: { count: { predicate: { gt: 0 } } } }
                ]
            }) {
                id
                fruits {
                    id
                }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    # Every color has at least one fruit, so the count > 0 predicate matches all of them.
    assert result.data["colors"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_aggregation_built_once_across_filter_and_order_by(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that the aggregation of a relation is built once when filtering and ordering by it.

    Filtering on one aggregation function and ordering by a *different* function of the same
    relation must reuse a single aggregation subquery; the snapshot shows one aggregation
    join, not two identically named ones.
    """
    query = """
        {
            colors(
                filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } },
                orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }
            ) {
                fruits {
                    id
                }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("distinct", "expected_count", "expected_color_indices"),
    [
        pytest.param(True, 2, [0, 2, 4], id="distinct-match"),
        pytest.param(False, 2, [0, 2, 4], id="non-distinct-match"),
        pytest.param(None, 2, [0, 2, 4], id="default-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter_with_distinct(
    distinct: bool | None,
    expected_count: int,
    expected_color_indices: list[int],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation with distinct option."""
    distinct_str = f"distinct: {to_graphql_representation(distinct, 'input')}" if distinct is not None else ""

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    count: {{
                        arguments: [name]
                        predicate: {{ eq: {expected_count} }}
                        {distinct_str}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {_COLORS[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_aggregate_filtered_and_selected_on_paginated_field(any_async_query: AnyQueryExecutor) -> None:
    """Test that filtering on an aggregate and selecting one leaves the parents uncrossed.

    Regression test for #224: the aggregate join was emitted without correlation to the
    pagination subquery, so every matching parent came back once per matching parent,
    carrying the others' counts.
    """
    query = """
        {
            colorsFilterablePaginated(
                filter: { fruitsAggregate: { sum: { arguments: [sweetness] predicate: { gt: 5 } } } }
                orderBy: { name: ASC }
            ) {
                name
                fruitsAggregate { count }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert result.data["colorsFilterablePaginated"] == [
        {"name": "Orange", "fruitsAggregate": {"count": 2}},
        {"name": "Pink", "fruitsAggregate": {"count": 2}},
        {"name": "Red", "fruitsAggregate": {"count": 2}},
        {"name": "Yellow", "fruitsAggregate": {"count": 3}},
    ]


async def test_aggregate_filtered_and_selected_paginates_matching_parents(
    any_async_query: AnyQueryExecutor,
) -> None:
    """Test that limit and offset index the parents the aggregate filter kept."""
    query = """
        {
            colorsFilterablePaginated(
                filter: { fruitsAggregate: { sum: { arguments: [sweetness] predicate: { gt: 5 } } } }
                orderBy: { name: ASC }
                offset: 1
                limit: 2
            ) {
                name
                fruitsAggregate { count }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert result.data["colorsFilterablePaginated"] == [
        {"name": "Pink", "fruitsAggregate": {"count": 2}},
        {"name": "Red", "fruitsAggregate": {"count": 2}},
    ]


def _order_by_keys(statement: str) -> list[str]:
    return [key.strip() for key in statement.rsplit("ORDER BY", 1)[1].split(",")]


@pytest.mark.snapshot
async def test_aggregation_filter_through_to_many_relation_also_selected(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a relation reached by an aggregation filter and selected is joined and ordered once."""
    query = """
        {
            colors(filter: { fruits: { farmsAggregate: { count: { predicate: { gt: 1 } } } } }) {
                id
                fruits { id }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert result.data["colors"] == [{"id": 1, "fruits": [{"id": 1}, {"id": 2}]}]

    assert query_tracker.query_count == 1
    order_by_keys = _order_by_keys(query_tracker[0].statement_str)
    assert len(order_by_keys) == len(set(order_by_keys))
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_aggregation_filter_through_to_one_relation_also_selected(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a to-one relation reached by an aggregation filter and selected is joined and ordered once."""
    query = """
        {
            fruits(filter: { color: { fruitsAggregate: { count: { predicate: { gt: 2 } } } } }) {
                id
                color { id }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert sorted(result.data["fruits"], key=lambda fruit: fruit["id"]) == [
        {"id": 3, "color": {"id": 2}},
        {"id": 4, "color": {"id": 2}},
        {"id": 5, "color": {"id": 2}},
    ]

    assert query_tracker.query_count == 1
    order_by_keys = _order_by_keys(query_tracker[0].statement_str)
    assert len(order_by_keys) == len(set(order_by_keys))
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_not_or_of_aggregation_and_to_many_through_to_one_relation(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """A relation-level ``_not`` of an OR on an aggregation and a to-many keeps the fruits of colors matching neither."""
    query = """
        {
            fruits(
                filter: {
                    color: {
                        _not: {
                            _or: [
                                { fruitsAggregate: { count: { predicate: { gt: 2 } } } }
                                { fruits: { name: { eq: "Apple" } } }
                            ]
                        }
                    }
                }
            ) {
                id
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert sorted(fruit["id"] for fruit in result.data["fruits"]) == [6, 7, 8, 9, 10]
    assert re.search(r"\) IS NOT (TRUE|1) ", query_tracker[0].statement_str, re.IGNORECASE)


async def test_aggregation_filter_through_relation_selected_with_its_own_ordering(
    any_async_query: AnyQueryExecutor,
) -> None:
    """Test that an ordered selection of a relation the filter also reaches keeps its own ordering."""
    query = """
        {
            colors(filter: { fruits: { farmsAggregate: { count: { predicate: { gt: 1 } } } } }) {
                id
                fruits(orderBy: { id: DESC }) { id }
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert result.data["colors"] == [{"id": 1, "fruits": [{"id": 2}, {"id": 1}]}]
