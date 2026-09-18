from __future__ import annotations

import pytest

from tests.integration.fixtures import QueryTracker
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

pytestmark = [pytest.mark.integration]


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
