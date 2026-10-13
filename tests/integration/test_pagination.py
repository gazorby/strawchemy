from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert, select

from strawchemy.schema.pagination import DefaultOffsetPagination
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Yellow is the only color holding three fruits, so `offset: 1` and `limit: 1, offset: 1` select different pages.
# Red, Green and Pink are the colors visible through `filter_statement`; their sweetness sums (13, 5, 18) are in a
# different order than the ids, and Yellow (6) would land between Green and Red if it leaked through the filter.
_COLORS: list[dict[str, Any]] = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Green"},
    {"id": 4, "name": "Pink"},
]
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 1, "water_percent": 0.88, "color_id": 2},
    {"id": 5, "name": "Quince", "sweetness": 3, "water_percent": 0.81, "color_id": 2},
    {"id": 6, "name": "Strawberry", "sweetness": 5, "water_percent": 0.91, "color_id": 3},
    {"id": 7, "name": "Cantaloupe", "sweetness": 0, "water_percent": 0.51, "color_id": 3},
    {"id": 8, "name": "Watermelon", "sweetness": 7, "water_percent": 0.92, "color_id": 4},
    {"id": 9, "name": "Pears", "sweetness": 11, "water_percent": 0.15, "color_id": 4},
]
# Apple, the first row of its page, holds several farms: they must not count as rows of the paginated relation.
_FRUIT_FARMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Apple farm 3", "fruit_id": 1},
    {"id": 4, "name": "Cherry farm", "fruit_id": 2},
    {"id": 5, "name": "Cherry farm 2", "fruit_id": 2},
    {"id": 6, "name": "Banana farm", "fruit_id": 3},
]
_VISIBLE_COLOR_NAMES = ["Red", "Green", "Pink"]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "farms"], scope="schema")
    class FruitType: ...

    # The order list also filters the order inputs of `fruits`: `sweetness` is the column the sum ordering aggregates.
    @strawchemy.type(
        Color, include=["id", "name", "fruits"], order=["id", "name", "sweetness", "fruits"], scope="schema"
    )
    class ColorType: ...

    @strawchemy.type(
        Color, include=["id", "name", "fruits"], order=["id", "name", "sweetness", "fruits"], paginate=["fruits"]
    )
    class ColorTypeWithPagination: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithDefaultPaginatedFruits:
        fruits: list[FruitType] = strawchemy.field(pagination=DefaultOffsetPagination(limit=1, offset=1))

    @strawchemy.aggregate(Fruit, include=["name"])
    class FruitAggregationType: ...

    @strawchemy.filter(Fruit, include=["name", "color"])
    class FruitFilter: ...

    @strawchemy.order(Color, include=["name", "fruits"])
    class ColorOrder: ...

    @strawberry.type
    class Query:
        fruits_paginated: list[FruitType] = strawchemy.field(filter_input=FruitFilter, pagination=True)
        fruit_aggregations_paginated: FruitAggregationType = strawchemy.field(root_aggregations=True, pagination=True)
        colors: list[ColorType] = strawchemy.field()
        colors_paginated: list[ColorTypeWithPagination] = strawchemy.field(pagination=True)
        colors_filtered_paginated: list[ColorType] = strawchemy.field(
            order_by_input=ColorOrder,
            pagination=True,
            filter_statement=lambda _: select(Color).where(Color.name.in_(_VISIBLE_COLOR_NAMES)),
        )
        colors_with_default_paginated_fruits: list[ColorWithDefaultPaginatedFruits] = strawchemy.field()

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FRUIT_FARMS)]


def _fruit_ids_of(color_id: int) -> list[dict[str, Any]]:
    return [
        {"id": fruit["id"]} for fruit in sorted(_FRUITS, key=lambda fruit: fruit["id"]) if fruit["color_id"] == color_id
    ]


async def test_pagination(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            {
                fruitsPaginated(offset: 1, limit: 1) {
                    name
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["fruitsPaginated"], list)
    assert len(result.data["fruitsPaginated"]) == 1
    assert result.data["fruitsPaginated"] == [{"name": "Cherry"}]


async def test_nested_pagination(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            {
                colorsPaginated(limit: 1) {
                    fruits(limit: 1) {
                        name
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["colorsPaginated"], list)
    assert len(result.data["colorsPaginated"]) == 1
    assert isinstance(result.data["colorsPaginated"][0]["fruits"], list)
    assert len(result.data["colorsPaginated"][0]["fruits"]) == 1


async def test_pagination_on_aggregation_query(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            {
                fruitAggregationsPaginated(offset: 1, limit: 1) {
                    nodes {
                        name
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert isinstance(result.data["fruitAggregationsPaginated"]["nodes"], list)
    assert len(result.data["fruitAggregationsPaginated"]["nodes"]) == 1
    assert result.data["fruitAggregationsPaginated"]["nodes"] == [{"name": "Cherry"}]


async def test_paginated_aggregate_only_selection(any_async_query: AnyQueryExecutor) -> None:
    """Keep aggregate-only selections on the pagination subquery alias."""
    plain = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    name
                    fruitsAggregate { count }
                }
            }
            """
        )
    )
    paginated = await maybe_async(
        any_async_query(
            """
            {
                colorsPaginated {
                    name
                    fruitsAggregate { count }
                }
            }
            """
        )
    )
    assert not plain.errors
    assert not paginated.errors
    assert plain.data
    assert paginated.data
    assert paginated.data["colorsPaginated"] == plain.data["colors"]


async def test_paginated_relationship_and_aggregate_selection(any_async_query: AnyQueryExecutor) -> None:
    """Keep relation loading and its aggregate compatible across pagination."""
    plain = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    name
                    fruits { name }
                    fruitsAggregate { count }
                }
            }
            """
        )
    )
    paginated = await maybe_async(
        any_async_query(
            """
            {
                colorsPaginated {
                    name
                    fruits { name }
                    fruitsAggregate { count }
                }
            }
            """
        )
    )
    assert not plain.errors
    assert not paginated.errors
    assert plain.data
    assert paginated.data
    assert paginated.data["colorsPaginated"] == plain.data["colors"]


async def test_ordered_relationship_and_aggregate_selection(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a relation with its own ordering can be selected next to an aggregate of the same relation."""
    result = await maybe_async(
        any_async_query("{ colors { id fruits(orderBy: { id: DESC }) { id } fruitsAggregate { count } } }")
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colors"]:
        fruits = _fruit_ids_of(color["id"])
        assert color["fruits"] == fruits[::-1]
        assert color["fruitsAggregate"] == {"count": len(fruits)}


async def test_pagination_ordered_by_aggregation(any_async_query: AnyQueryExecutor) -> None:
    """Test paginating a query ordered by an aggregation of a relation.

    Guards the order-by-aggregation KeyError fix in ``SubqueryBuilder.build``: combining a
    LIMIT with an aggregation order key must resolve the aggregation column rather than raise.
    """
    result = await maybe_async(
        any_async_query(
            """
            {
                colorsFilteredPaginated(limit: 2, orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
                    name
                    fruitsAggregate { count }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    # colorsFilteredPaginated is restricted to {Red, Green, Pink} by its filter_statement.
    # sum(fruit.sweetness) per candidate color: Green=5+0=5, Red=4+9=13, Pink=7+11=18.
    # Ascending, limited to 2 -> Green, Red.
    assert result.data["colorsFilteredPaginated"] == [
        {"name": "Green", "fruitsAggregate": {"count": 2}},
        {"name": "Red", "fruitsAggregate": {"count": 2}},
    ]


async def test_pagination_ordered_by_unselected_aggregation(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """An aggregation used only as an order key is computed once, inside the pagination subquery."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colorsFilteredPaginated(limit: 2, orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
                    name
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    # sum(fruit.sweetness) over {Red, Green, Pink}: Green=5, Red=13, Pink=18 -> Green, Red.
    assert result.data["colorsFilteredPaginated"] == [{"name": "Green"}, {"name": "Red"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("sum(") == 1


async def test_pagination_with_relation_filter(any_async_query: AnyQueryExecutor, query_tracker: QueryTracker) -> None:
    """A relation filter under pagination selects the filtered rows, without duplicating them."""
    result = await maybe_async(
        any_async_query(
            """
            {
                fruitsPaginated(limit: 5, filter: { color: { name: { eq: "Red" } } }) {
                    name
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["fruitsPaginated"] == [{"name": "Apple"}, {"name": "Cherry"}]
    assert query_tracker.query_count == 1


async def test_nested_pagination_default_limit_and_offset(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a nested paginated relation selected without arguments gets its default limit and offset."""
    result = await maybe_async(any_async_query("{ colorsWithDefaultPaginatedFruits { id fruits { id } } }"))
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(color["id"])[1:2]


async def test_nested_pagination_explicit_null_limit_disables_default(any_async_query: AnyQueryExecutor) -> None:
    """Test that an explicit null limit on a nested paginated relation lifts its default limit."""
    result = await maybe_async(
        any_async_query("{ colorsWithDefaultPaginatedFruits { id fruits(limit: null, offset: 0) { id } } }")
    )
    assert not result.errors
    assert result.data
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(color["id"])


@pytest.mark.parametrize(
    ("root_field", "explicit_arguments"),
    [
        pytest.param("colorsWithDefaultPaginatedFruits", "limit: 1, offset: 1", id="custom-default"),
        pytest.param("colorsPaginated", "limit: 100", id="config-default"),
    ],
)
async def test_nested_pagination_explicit_default_shares_join_with_omitted(
    root_field: str,
    explicit_arguments: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that an alias spelling out the default pagination shares the join of an alias omitting it."""
    result = await maybe_async(
        any_async_query(f"{{ {root_field} {{ id a: fruits {{ id }} b: fruits({explicit_arguments}) {{ id }} }} }}")
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in result.data[root_field]:
        assert color["a"] == color["b"]
        assert color["a"] == (
            _fruit_ids_of(color["id"])[1:2]
            if root_field == "colorsWithDefaultPaginatedFruits"
            else _fruit_ids_of(color["id"])
        )


async def test_nested_pagination_variables_holding_defaults_share_join_with_omitted(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that nested pagination arguments bound to variables holding the defaults share the omitted form's join."""
    result = await maybe_async(
        any_async_query(
            """
            query ($l: Int, $o: Int!) {
                colorsWithDefaultPaginatedFruits { id a: fruits { id } b: fruits(limit: $l, offset: $o) { id } }
            }
            """,
            {"l": 1, "o": 1},
        )
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["a"] == color["b"] == _fruit_ids_of(color["id"])[1:2]


async def test_nested_pagination_defaults_apply_in_fragment(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a nested paginated relation selected through a fragment gets its default limit and offset."""
    result = await maybe_async(
        any_async_query(
            """
            fragment ColorFruits on ColorWithDefaultPaginatedFruits { fruits { id } }
            { colorsWithDefaultPaginatedFruits { id ...ColorFruits } }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(color["id"])[1:2]


@pytest.mark.parametrize(
    ("operation", "variables", "expected"),
    [
        pytest.param("query ($l: Int, $o: Int)", {}, slice(1, 2), id="omitted-variables"),
        pytest.param("query ($l: Int, $o: Int)", {"l": None}, slice(1, None), id="null-limit-variable"),
        pytest.param("query ($l: Int = 1, $o: Int = 0)", {}, slice(0, 1), id="operation-defaults"),
        pytest.param("query ($l: Int = 1, $o: Int = 0)", {"l": None}, slice(0, None), id="null-overrides-default"),
    ],
)
async def test_nested_pagination_variables(
    operation: str,
    variables: dict[str, Any],
    expected: slice,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that nested pagination variables fall back to their operation default, then the argument default."""
    result = await maybe_async(
        any_async_query(
            f"{operation} {{ colorsWithDefaultPaginatedFruits {{ id fruits(limit: $l, offset: $o) {{ id }} }} }}",
            variables,
        )
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(color["id"])[expected]


async def test_nested_config_default_limit_with_omitted_variable(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a nested limit bound to an omitted variable keeps the configured default limit."""
    result = await maybe_async(
        any_async_query("query ($l: Int) { colorsPaginated { id a: fruits { id } b: fruits(limit: $l) { id } } }", {})
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in result.data["colorsPaginated"]:
        assert color["a"] == color["b"]


@pytest.mark.parametrize(
    "order_by",
    [
        pytest.param("", id="no-order-by"),
        pytest.param("orderBy: [{ color: { name: ASC } }]", id="tied-order-by"),
    ],
)
@pytest.mark.parametrize(
    ("pagination", "expected"),
    [
        pytest.param("limit: 1", slice(0, 1), id="limit"),
        pytest.param("offset: 1", slice(1, None), id="offset"),
        pytest.param("limit: 1, offset: 1", slice(1, 2), id="limit-offset"),
    ],
)
async def test_nested_pagination_counts_tied_rows(
    order_by: str,
    pagination: str,
    expected: slice,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    db_features: DatabaseFeatures,
) -> None:
    """Test that nested limit and offset count rows tied on the ordering one by one."""
    result = await maybe_async(
        any_async_query(f"{{ colorsPaginated {{ id fruits({order_by} {pagination}) {{ id }} }} }}")
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsPaginated"]:
        color_fruits = _fruit_ids_of(color["id"])
        assert len(color["fruits"]) == len(color_fruits[expected])
        assert all(fruit in color_fruits for fruit in color["fruits"])
        # PostgreSQL's LATERAL LIMIT picks any of the tied rows; the rank breaks ties by primary key.
        if not db_features.supports_lateral:
            assert color["fruits"] == color_fruits[expected]


@pytest.mark.parametrize(
    ("pagination", "expected"),
    [
        pytest.param("limit: 1", slice(0, 1), id="limit"),
        pytest.param("offset: 1", slice(1, None), id="offset"),
        pytest.param("limit: 1, offset: 1", slice(1, 2), id="limit-offset"),
    ],
)
async def test_nested_pagination_counts_tied_rows_with_to_many_child(
    pagination: str,
    expected: slice,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    db_features: DatabaseFeatures,
) -> None:
    """Test that the to-many children of a nested paginated relation do not count as rows of that relation."""
    result = await maybe_async(
        any_async_query(
            f"""
            {{
                colorsPaginated {{
                    id
                    fruits(orderBy: [{{ color: {{ name: ASC }} }}], {pagination}) {{ id farms {{ id }} }}
                }}
            }}
            """
        )
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsPaginated"]:
        color_fruits = _fruit_ids_of(color["id"])
        assert len(color["fruits"]) == len(color_fruits[expected])
        if not db_features.supports_lateral:
            assert [{"id": fruit["id"]} for fruit in color["fruits"]] == color_fruits[expected]
        for fruit in color["fruits"]:
            assert {"id": fruit["id"]} in color_fruits
            farm_ids = sorted(farm["id"] for farm in fruit["farms"])
            assert farm_ids == [farm["id"] for farm in _FRUIT_FARMS if farm["fruit_id"] == fruit["id"]]
