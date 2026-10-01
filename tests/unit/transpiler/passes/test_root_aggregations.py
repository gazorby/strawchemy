"""Tests for the ``RootAggregations`` pass: window functions over the root rows."""

from __future__ import annotations

import pytest

from tests.unit.transpiler.passes.utils import outer_projection, plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])


@_DIALECTS
def test_root_aggregation_over_page(dialect_name: str) -> None:
    """A root aggregation of paginated rows is a window function of the outer SELECT, computed over the page."""
    lines = plan_sql("{ colorAggregationsPaginated(limit: 2) { aggregations { count } nodes { name } } }", dialect_name)

    limit = next(index for index, line in enumerate(lines) if "LIMIT" in line)
    page_end = next(index for index, line in enumerate(lines) if line.startswith("       ) AS color"))
    assert limit < page_end
    assert [column for column in outer_projection(lines) if "OVER" in column] == ["count(*) OVER () AS anon_1"]
    assert sum("OVER ()" in line for line in lines) == 1


@_DIALECTS
def test_root_aggregation_reads_root_alias(dialect_name: str) -> None:
    """Without pagination, the window functions read the root alias, one per selected argument."""
    lines = plan_sql(
        "{ colorAggregationsPaginated { aggregations { count max { name } } nodes { id } } }", dialect_name
    )

    assert [column for column in outer_projection(lines) if "OVER" in column] == [
        "count(*) OVER () AS anon_1",
        "max(color.name) OVER () AS anon_2",
    ]
