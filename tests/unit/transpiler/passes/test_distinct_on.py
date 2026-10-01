"""Tests for the ``DistinctOn`` pass: native or emulated DISTINCT ON, and the page it runs in."""

from __future__ import annotations

import pytest

from tests.unit.transpiler.passes.utils import plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])


def _one_line_sql(query: str, dialect_name: str) -> str:
    return " ".join(" ".join(plan_sql(query, dialect_name)).split())


@_DIALECTS
def test_distinct_native_vs_emulated(dialect_name: str) -> None:
    """DISTINCT ON is native on postgresql when the ORDER BY starts with its columns, a ``row_number`` rank elsewhere."""
    sql = _one_line_sql("{ colorsDistinct(distinctOn: [name], orderBy: { name: ASC }) { name } }", dialect_name)

    if dialect_name == "postgresql":
        assert "SELECT DISTINCT ON (color.name)" in sql
        assert "row_number()" not in sql
    else:
        assert "row_number() OVER (PARTITION BY color.name ORDER BY color.name ASC)" in sql
        assert "DISTINCT" not in sql


def test_distinct_without_order_prefix_is_emulated() -> None:
    """On postgresql, an ORDER BY not starting with the DISTINCT ON columns makes DISTINCT ON a ``row_number`` rank."""
    sql = _one_line_sql("{ colorsDistinct(distinctOn: [name], orderBy: { id: ASC }) { name } }", "postgresql")

    assert "row_number() OVER (PARTITION BY color.name ORDER BY color.id ASC)" in sql
    assert "DISTINCT ON" not in sql


def test_distinct_on_more_columns_than_order_by_is_emulated() -> None:
    """On postgresql, an ORDER BY shorter than the DISTINCT ON columns makes DISTINCT ON a ``row_number`` rank."""
    sql = _one_line_sql("{ colorsDistinct(distinctOn: [name, id], orderBy: { name: ASC }) { name } }", "postgresql")

    assert "row_number() OVER (PARTITION BY color.name, color.id ORDER BY color.name ASC)" in sql
    assert "DISTINCT ON" not in sql


@_DIALECTS
def test_distinct_selecting_relation_wraps(dialect_name: str) -> None:
    """DISTINCT ON next to a selected to-many relation runs in the page, the relation is joined outside it."""
    lines = plan_sql(
        "{ colorsDistinct(distinctOn: [name], orderBy: { name: ASC }) { name fruits { name } } }", dialect_name
    )

    page_end = next(index for index, line in enumerate(lines) if line.startswith("       ) AS color"))
    join = next(index for index, line in enumerate(lines) if "JOIN fruit" in line)
    assert join > page_end
    assert sum("FROM color AS color" in line for line in lines) == 1
