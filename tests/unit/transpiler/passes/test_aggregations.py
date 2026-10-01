"""Tests for the ``Aggregations`` pass: selected aggregates of relations, read from the join computing them."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests.unit.transpiler.passes.utils import coalesced, outer_projection, plan_sql

if TYPE_CHECKING:
    from collections.abc import Callable

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
_CTE = re.compile(r"\banon_\d+ AS \(")


@_DIALECTS
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            """{ colorsPaginated(limit: 2, filter: { fruitsAggregate: { count: { predicate: { gt: 1 } } } }) {
                id fruitsAggregate { sum { sweetness } } } }""",
            lambda _: ["color.id", "color.sum_1"],
            id="filter-only-paginated",
        ),
        pytest.param(
            """{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 1 } } } }) {
                id fruitsAggregate { sum { sweetness } } } }""",
            lambda _: ["color.id", "anon_1.sum_1"],
            id="filter-only",
        ),
        pytest.param(
            """{ colors(orderBy: { fruitsAggregate: { avg: { sweetness: ASC } } }) {
                id fruitsAggregate { count } } }""",
            lambda dialect_name: ["color.id", coalesced("anon_1.count_1", dialect_name)],
            id="order-by-only",
        ),
        pytest.param(
            """{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 1 } } } }) {
                id fruitsAggregate { count } } }""",
            lambda dialect_name: ["color.id", coalesced("anon_1.count_1", dialect_name)],
            id="filtered-and-selected",
        ),
        pytest.param(
            """{ groups(filter: { color: { fruitsAggregate: { count: { predicate: { gt: 1 } } } } }) {
                id color { id fruitsAggregate { sum { sweetness } } } } }""",
            lambda dialect_name: [
                "`group`.id" if dialect_name == "mysql" else '"group".id',
                "color_1.id AS id_1",
                "color_1.id AS group__color__id",
                "anon_1.sum_1",
            ],
            id="nested-filter-only",
        ),
    ],
)
def test_selects_only_requested_functions(dialect_name: str, query: str, expected: Callable[[str], list[str]]) -> None:
    """A function only the filter or the ordering needs is computed by the join but never reaches the SELECT list."""
    assert outer_projection(plan_sql(query, dialect_name)) == expected(dialect_name)


@_DIALECTS
@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            "{ colors(orderBy: { fruitsAggregate: { count: ASC } }) { fruitsAggregate { count } } }",
            id="output-order-by",
        ),
        pytest.param(
            "{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } }) { fruitsAggregate { count } } }",
            id="output-filter",
        ),
        pytest.param(
            """{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } },
                orderBy: { fruitsAggregate: { avg: { sweetness: ASC } } }) { fruits { id } } }""",
            id="filter-order-by",
        ),
        pytest.param(
            """{ colors(filter: { fruitsAggregate: { avg: { arguments: [sweetness] predicate: { gt: 0 } } } },
                orderBy: { fruitsAggregate: { avg: { sweetness: ASC } } }) { fruits { id } } }""",
            id="filter-order-by-same-aggregation",
        ),
        pytest.param(
            "{ colors { fruitsAggregate { max { sweetness name } } } }",
            id="output-multiple-aggregations",
        ),
        pytest.param(
            """{ colors(filter: { fruitsAggregate: {
                sum: { arguments: [sweetness], predicate: { gt: 0 } },
                avg: { arguments: [sweetness], predicate: { gt: 0 } } } }) { fruits { id } } }""",
            id="filter-multiple-aggregations",
        ),
        pytest.param(
            """{ colors(orderBy: { fruitsAggregate: { sum: { sweetness: ASC }, avg: { sweetness: ASC } } }) {
                fruits { id } } }""",
            id="order-by-multiple-aggregations",
        ),
        pytest.param(
            """{ colors(orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
                id fruitsAggregate { count } } }""",
            id="order-by-and-selected-functions",
        ),
    ],
)
def test_filter_order_select_share_one_join(dialect_name: str, query: str) -> None:
    """Filtering, ordering and selecting functions of one aggregation compute them in a single LATERAL or CTE."""
    sql = "\n".join(plan_sql(query, dialect_name))

    if dialect_name == "postgresql":
        assert sql.count("LATERAL") == 1
        assert "WITH" not in sql
    else:
        assert len(_CTE.findall(sql)) == 1
        assert "LATERAL" not in sql


@_DIALECTS
def test_relation_level_selects_its_aggregate(dialect_name: str) -> None:
    """An aggregate selected under a relation is computed per related row, correlated to the relation's alias."""
    lines = plan_sql("{ groups { color { fruitsAggregate { count } } } }", dialect_name)
    sql = "\n".join(lines)

    if dialect_name == "postgresql":
        assert sql.count("LATERAL") == 1
        assert "color_1.id = fruit_1.color_id" in sql
    else:
        assert len(_CTE.findall(sql)) == 1
    assert any("count_1" in column for column in outer_projection(lines))


@pytest.mark.parametrize("dialect_name", ["sqlite", "mysql"])
def test_aggregate_at_two_levels_shares_one_grouped_cte(dialect_name: str) -> None:
    """Without LATERAL, one aggregate selected at two levels joins one grouped CTE, once per level."""
    lines = plan_sql(
        "{ colors { fruitsAggregate { count } fruits { color { fruitsAggregate { count } } } } }", dialect_name
    )
    sql = "\n".join(lines)

    ctes = _CTE.findall(sql)
    assert len(ctes) == 1
    cte = ctes[0].removesuffix(" AS (")
    joins = [line.strip() for line in lines if "JOIN anon" in line]
    assert len(joins) == 2
    assert joins[0] == f"LEFT OUTER JOIN {cte}"
    assert re.fullmatch(rf"LEFT OUTER JOIN {cte} AS anon_\d+", joins[1])
