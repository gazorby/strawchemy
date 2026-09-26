from __future__ import annotations

from typing import Any

import pytest

from tests.integration.fixtures import QueryTracker
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

pytestmark = [pytest.mark.integration]


def _fruit_ids_of(raw_fruits: RawRecordData, color_id: int) -> list[dict[str, Any]]:
    return [
        {"id": fruit["id"]}
        for fruit in sorted(raw_fruits, key=lambda fruit: fruit["id"])
        if fruit["color_id"] == color_id
    ]


async def test_pagination(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
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


async def test_nested_pagination(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
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


async def test_pagination_on_aggregation_query(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
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


async def test_paginated_aggregate_only_selection(any_query: AnyQueryExecutor) -> None:
    """Keep aggregate-only selections on the pagination subquery alias."""
    plain = await maybe_async(
        any_query(
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
        any_query(
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


async def test_paginated_relationship_and_aggregate_selection(any_query: AnyQueryExecutor) -> None:
    """Keep relation loading and its aggregate compatible across pagination."""
    plain = await maybe_async(
        any_query(
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
        any_query(
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
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that a relation with its own ordering can be selected next to an aggregate of the same relation."""
    result = await maybe_async(
        any_query("{ colors { id fruits(orderBy: { id: DESC }) { id } fruitsAggregate { count } } }")
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colors"]:
        fruits = _fruit_ids_of(raw_fruits, color["id"])
        assert color["fruits"] == fruits[::-1]
        assert color["fruitsAggregate"] == {"count": len(fruits)}


async def test_pagination_ordered_by_aggregation(any_query: AnyQueryExecutor) -> None:
    """Test paginating a query ordered by an aggregation of a relation.

    Guards the order-by-aggregation KeyError fix in ``SubqueryBuilder.build``: combining a
    LIMIT with an aggregation order key must resolve the aggregation column rather than raise.
    """
    result = await maybe_async(
        any_query(
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
    any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """An aggregation used only as an order key is computed once, inside the pagination subquery."""
    result = await maybe_async(
        any_query(
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


async def test_pagination_with_relation_filter(any_query: AnyQueryExecutor, query_tracker: QueryTracker) -> None:
    """A relation filter under pagination selects the filtered rows, without duplicating them."""
    result = await maybe_async(
        any_query(
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
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that a nested paginated relation selected without arguments gets its default limit and offset."""
    result = await maybe_async(any_query("{ colorsWithDefaultPaginatedFruits { id fruits { id } } }"))
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(raw_fruits, color["id"])[1:2]


async def test_nested_pagination_explicit_null_limit_disables_default(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData
) -> None:
    """Test that an explicit null limit on a nested paginated relation lifts its default limit."""
    result = await maybe_async(
        any_query("{ colorsWithDefaultPaginatedFruits { id fruits(limit: null, offset: 0) { id } } }")
    )
    assert not result.errors
    assert result.data
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(raw_fruits, color["id"])


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
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    raw_fruits: RawRecordData,
) -> None:
    """Test that an alias spelling out the default pagination shares the join of an alias omitting it."""
    result = await maybe_async(
        any_query(f"{{ {root_field} {{ id a: fruits {{ id }} b: fruits({explicit_arguments}) {{ id }} }} }}")
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in result.data[root_field]:
        assert color["a"] == color["b"]
        assert color["a"] == (
            _fruit_ids_of(raw_fruits, color["id"])[1:2]
            if root_field == "colorsWithDefaultPaginatedFruits"
            else _fruit_ids_of(raw_fruits, color["id"])
        )


async def test_nested_pagination_variables_holding_defaults_share_join_with_omitted(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that nested pagination arguments bound to variables holding the defaults share the omitted form's join."""
    result = await maybe_async(
        any_query(
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
        assert color["a"] == color["b"] == _fruit_ids_of(raw_fruits, color["id"])[1:2]


async def test_nested_pagination_defaults_apply_in_fragment(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that a nested paginated relation selected through a fragment gets its default limit and offset."""
    result = await maybe_async(
        any_query(
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
        assert color["fruits"] == _fruit_ids_of(raw_fruits, color["id"])[1:2]


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
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    raw_fruits: RawRecordData,
) -> None:
    """Test that nested pagination variables fall back to their operation default, then the argument default."""
    result = await maybe_async(
        any_query(
            f"{operation} {{ colorsWithDefaultPaginatedFruits {{ id fruits(limit: $l, offset: $o) {{ id }} }} }}",
            variables,
        )
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    for color in result.data["colorsWithDefaultPaginatedFruits"]:
        assert color["fruits"] == _fruit_ids_of(raw_fruits, color["id"])[expected]


async def test_nested_config_default_limit_with_omitted_variable(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a nested limit bound to an omitted variable keeps the configured default limit."""
    result = await maybe_async(
        any_query("query ($l: Int) { colorsPaginated { id a: fruits { id } b: fruits(limit: $l) { id } } }", {})
    )
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in result.data["colorsPaginated"]:
        assert color["a"] == color["b"]
