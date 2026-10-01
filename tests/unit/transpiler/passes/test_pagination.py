"""Tests for the ``OffsetPagination`` pass: the root page subquery and what it exports."""

from __future__ import annotations

import pytest

from tests.unit.transpiler.passes.utils import coalesced, outer_order_by, outer_projection, plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])


def _page_end(lines: list[str]) -> int:
    return next(index for index, line in enumerate(lines) if line.startswith("       ) AS color"))


@_DIALECTS
def test_pagination_wraps_and_counts_roots(dialect_name: str) -> None:
    """A limit runs in a page subquery of the root rows, and a selected to-many relation is joined outside it."""
    lines = plan_sql("{ colorsPaginated(limit: 2) { fruits { name } } }", dialect_name)

    page_end = _page_end(lines)
    limit = next(index for index, line in enumerate(lines) if "LIMIT" in line)
    join = next(index for index, line in enumerate(lines) if "JOIN fruit" in line)
    assert limit < page_end < join
    assert sum("FROM color AS color" in line for line in lines) == 1
    assert outer_order_by(lines) == ["color.id ASC", "fruit_1.id ASC"]


@_DIALECTS
@pytest.mark.parametrize(
    ("query", "expected_order_by", "expected_selected"),
    [
        pytest.param(
            """{ colorsPaginated(limit: 2, orderBy: { fruitsAggregate: { sum: { sweetness: ASC } } }) {
                id fruitsAggregate { count } } }""",
            ["color.sum_1 ASC"],
            ["color.count_1"],
            id="selected-function-hoisted",
        ),
        pytest.param(
            """{ colorsPaginated(limit: 2, filter: { fruitsAggregate: { count: { predicate: { gt: 1 } } } }) {
                id fruitsAggregate { sum { sweetness } } } }""",
            ["color.id ASC"],
            ["color.sum_1"],
            id="filtered-function-hoisted",
        ),
        pytest.param(
            """{ colorsPaginated(limit: 2, filter: { fruitsAggregate: {
                count: { predicate: { gt: 1 } }, sum: { arguments: [sweetness], predicate: { gt: 0 } } } }) {
                id fruitsAggregate { count sum { sweetness } } } }""",
            ["color.id ASC"],
            ["color.count_1", "color.sum_1"],
            id="two-functions-filtered-and-selected",
        ),
    ],
)
def test_pagination_hoists_aggregate(
    dialect_name: str, query: str, expected_order_by: list[str], expected_selected: list[str]
) -> None:
    """An aggregate the paginated rows use is joined once, inside the page, and the outer query reads it from the page."""
    lines = plan_sql(query, dialect_name)

    page_end = _page_end(lines)
    if dialect_name == "postgresql":
        laterals = [index for index, line in enumerate(lines) if "LATERAL" in line]
        assert len(laterals) == 1
        assert laterals[0] < page_end
    else:
        assert sum(line.startswith("WITH") for line in lines) == 1
        aggregate_joins = [index for index, line in enumerate(lines) if "JOIN anon_1" in line]
        assert len(aggregate_joins) == 1
        assert aggregate_joins[0] < page_end
    assert outer_order_by(lines) == expected_order_by
    expected = [coalesced(column, dialect_name) if "count" in column else column for column in expected_selected]
    assert [column for column in outer_projection(lines) if column != "color.id"] == expected
