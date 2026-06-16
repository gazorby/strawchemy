"""Equivalence harness: plan/emit SQL must match legacy _build_query output for supported shapes (root/relation/aggregation)."""

from __future__ import annotations

import pytest

from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

pytestmark = [pytest.mark.integration]


@pytest.fixture
def plan_equivalence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enables the env-gated plan/legacy equivalence assertion for the test."""
    monkeypatch.setenv("STRAWCHEMY_PLAN_EQUIVALENCE", "1")


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ colors { name } }", id="plain-select"),
        pytest.param('{ colors(filter: { name: { eq: "red" } }) { name } }', id="filtered"),
        pytest.param("{ colors(orderBy: { name: ASC }) { name } }", id="ordered"),
        pytest.param("{ colors(orderBy: { name: ASC_NULLS_LAST }) { name } }", id="ordered-nulls"),
    ],
)
async def test_leaf_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """For leaf-shaped queries the plan/emit SQL is byte-identical to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ colors { name fruits { name } } }", id="relation-nested-select"),
        pytest.param('{ colors(filter: { fruits: { name: { eq: "apple" } } }) { name } }', id="filter-by-relation"),
        pytest.param(
            "{ colors { name fruits(orderBy: { sweetness: ASC }) { name sweetness } } }",
            id="nested-relation-order-sweetness",
        ),
        pytest.param("{ colors { name fruits(orderBy: { name: ASC }) { name } } }", id="nested-relation-order"),
    ],
)
async def test_relation_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """Relation-join queries emit byte-identical SQL to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ colors { name fruitsAggregate { count } } }", id="output-aggregation"),
        pytest.param(
            "{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } }) { name } }",
            id="filter-by-aggregation",
        ),
        pytest.param(
            "{ colors(orderBy: { fruitsAggregate: { count: ASC } }) { fruitsAggregate { count } } }",
            id="order-by-aggregation",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { sum { sweetness } avg { waterPercent } } } }",
            id="multi-output-aggregation",
        ),
    ],
)
async def test_aggregation_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """Aggregation queries emit byte-identical SQL to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            "{ fruitAggregations { aggregations { sum { sweetness } } nodes { id } } }",
            id="root-aggregation",
        ),
    ],
)
async def test_root_aggregation_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """Root-aggregation queries (window over) emit byte-identical SQL to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ fruitsHooks { description } }", id="hook-load-columns"),
        pytest.param("{ fruitsHooks { prettyColor } }", id="hook-load-relationships"),
        pytest.param("{ filteredFruits { name } }", id="hook-custom-where"),
        pytest.param("{ orderedFruits { waterPercent } }", id="hook-custom-order"),
        pytest.param("{ colorsHooks { id fruits { prettyColor } } }", id="hook-on-nested-field"),
        pytest.param("{ colorsWithFilteredFruits { fruits { name } } }", id="hook-on-type"),
    ],
)
async def test_hook_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """Query-hook queries emit byte-identical main SQL to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data


@pytest.mark.usefixtures("plan_equivalence")
@pytest.mark.parametrize(
    "query",
    [
        pytest.param("{ colorsPaginated(limit: 2) { name } }", id="root-limit"),
        pytest.param("{ fruitsPaginated(offset: 1, limit: 1) { name } }", id="root-limit-offset"),
        pytest.param("{ users(distinctOn: [name]) { id name } }", id="distinct-on"),
        pytest.param(
            "{ users(distinctOn: [name], orderBy: [{name: ASC}, {id: DESC}]) { id name } }",
            id="distinct-on-ordered",
        ),
        pytest.param(
            "{ colorsPaginated(limit: 1) { name fruits(limit: 1) { name } } }",
            id="paginated-with-relation",
        ),
    ],
)
async def test_pagination_distinct_plan_matches_legacy(query: str, any_query: AnyQueryExecutor) -> None:
    """Pagination and DISTINCT ON queries emit byte-identical SQL to legacy (asserted in-build)."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data
