from __future__ import annotations

import pytest

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
    assert result.data["colorsFilteredPaginated"] == [{"name": "Green"}, {"name": "Red"}]
