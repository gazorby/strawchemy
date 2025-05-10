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
