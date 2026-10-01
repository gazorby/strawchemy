"""Tests for the ``QueryHooks`` pass: hook edits on a level's rows and hook loads in its projection."""

from __future__ import annotations

import pytest

from tests.unit.transpiler.passes.utils import outer_projection, plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])

_FILTERED_ON_COLOR = '(filter: { color: { name: { eq: "red" } } })'


def _joins(lines: list[str]) -> list[str]:
    return [line.strip().replace("INNER JOIN", "JOIN") for line in lines if "JOIN" in line]


def _one_line(lines: list[str]) -> str:
    """Returns ``lines`` as one line without identifier quotes, a MySQL ``INNER JOIN`` written ``JOIN``."""
    return " ".join(" ".join(lines).split()).replace('"', "").replace("`", "").replace("INNER JOIN", "JOIN")


def _page(lines: list[str]) -> list[str]:
    """Returns the lines of the page subquery, between the outer ``FROM (`` and the line closing it."""
    start = lines.index("  FROM (")
    end = next(index for index, line in enumerate(lines) if index > start and line.startswith("       ) AS"))
    return lines[start + 1 : end]


@_DIALECTS
def test_hook_where_on_relation_in_on_clause(dialect_name: str) -> None:
    """A to-many relation whose hook adds only a WHERE is a plain LEFT OUTER JOIN carrying it in its ON clause."""
    lines = plan_sql("{ colorsSweetFruits { name fruits { name } } }", dialect_name)
    sql = _one_line(lines)

    assert _joins(lines) == ["LEFT OUTER JOIN fruit AS fruit_1"]
    assert "ON color.id = fruit_1.color_id AND fruit_1.sweetness >" in sql
    assert "LATERAL" not in sql
    assert not sql.startswith("WITH")


@_DIALECTS
def test_hooked_to_one_filtered_and_selected_joins_twice(dialect_name: str) -> None:
    """A to-one relation filtered and selected through a WHERE hook is joined twice, the selection with the hook."""
    lines = plan_sql(f"{{ groupsVisibleColor{_FILTERED_ON_COLOR} {{ name color {{ name }} }} }}", dialect_name)
    sql = _one_line(lines)

    assert _joins(lines) == ["JOIN color AS color_2", "LEFT OUTER JOIN color AS color_1"]
    assert "ON color_2.id = group.color_id LEFT OUTER JOIN" in sql
    assert "ON color_1.id = group.color_id AND color_1.name !=" in sql


@_DIALECTS
def test_filter_on_hooked_relation_no_subquery(dialect_name: str) -> None:
    """Without pagination, a filter on a hooked to-one relation joins it in the query itself, with no subquery."""
    lines = plan_sql(f"{{ groupsVisibleColor{_FILTERED_ON_COLOR} {{ name color {{ name }} }} }}", dialect_name)

    assert sum("SELECT" in line for line in lines) == 1
    assert not any("LATERAL" in line for line in lines)


@_DIALECTS
def test_filter_on_hooked_relation_paginated_joins_hook_outside_page(dialect_name: str) -> None:
    """With pagination, the filter join runs inside the page and the hooked selection join outside it."""
    lines = plan_sql(
        '{ groupsVisibleColorPaginated(limit: 2, filter: { color: { name: { eq: "red" } } }) { name color { name } } }',
        dialect_name,
    )
    page = _page(lines)

    assert _joins(page) == ["JOIN color AS color_2"]
    assert [join for join in _joins(lines) if join not in _joins(page)] == ["LEFT OUTER JOIN color AS color_1"]


@_DIALECTS
def test_root_hook_join_with_pagination(dialect_name: str) -> None:
    """A root hook adding a JOIN runs inside the page, which exports the columns the hook loads."""
    lines = plan_sql("{ coloredFruitsPaginated(limit: 2) { name } }", dialect_name)
    page = _page(lines)

    assert _joins(page) == ["JOIN color AS hook_color"]
    assert not any("hook_color" in line for line in lines if line not in page)
    assert any("fruit.sweetness" in line for line in page)
    assert "fruit.sweetness" in outer_projection(lines)


@_DIALECTS
def test_hook_order_only_to_one_reuses_row_join(dialect_name: str) -> None:
    """A to-one relation ordered on and selected, whose hook adds only an ORDER BY, is joined once."""
    lines = plan_sql(
        "{ groupsNameOrderedColor(orderBy: { color: { name: ASC } }) { name color { name } } }", dialect_name
    )

    assert _joins(lines) == ["LEFT OUTER JOIN color AS color_1"]


@_DIALECTS
def test_root_hook_order_only_orders_inline(dialect_name: str) -> None:
    """A root hook adding only an ORDER BY orders the root rows in the query itself, with no subquery."""
    lines = plan_sql("{ nameOrderedColors { id name } }", dialect_name)

    assert sum("SELECT" in line for line in lines) == 1
    assert "FROM color AS color ORDER BY color.name ASC" in _one_line(lines)


@_DIALECTS
def test_root_hook_join_without_pagination_joins_inline(dialect_name: str) -> None:
    """Without pagination, a root hook adding a JOIN joins in the query itself, with no subquery."""
    lines = plan_sql("{ coloredFruits { name } }", dialect_name)

    assert sum("SELECT" in line for line in lines) == 1
    assert _joins(lines) == ["JOIN color AS hook_color"]


@_DIALECTS
def test_root_hook_limit_runs_in_a_page_before_to_many_joins(dialect_name: str) -> None:
    """A root hook adding a LIMIT limits the root rows in a page subquery, and the to-many join runs outside it."""
    lines = plan_sql("{ firstColors { name fruits { name } } }", dialect_name)
    page = _page(lines)

    assert any("LIMIT" in line for line in page)
    assert not _joins(page)
    assert [join for join in _joins(lines) if join not in _joins(page)] == ["LEFT OUTER JOIN fruit AS fruit_1"]
