"""Tests for the ``Selection`` pass: loaded columns and identity columns of one level."""

from __future__ import annotations

import pytest

from tests.unit.transpiler.passes.utils import outer_projection, plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])


def _select_list(lines: list[str]) -> list[str]:
    return lines[: next(index for index, line in enumerate(lines) if line.lstrip().startswith("FROM"))]


@_DIALECTS
def test_selection_loads_only_selected_columns(dialect_name: str) -> None:
    """A selection of one column loads that column and the primary key, and no other column."""
    lines = plan_sql("{ colors { name } }", dialect_name)

    assert sorted(line.removeprefix("SELECT").strip(" ,") for line in _select_list(lines)) == ["color.id", "color.name"]


@_DIALECTS
def test_selection_loads_primary_key_without_columns(dialect_name: str) -> None:
    """A level selecting only a relation still loads its primary key, not its other columns."""
    lines = plan_sql("{ colors { fruits { name } } }", dialect_name)

    color_columns = [line for line in _select_list(lines) if "color." in line]
    assert color_columns == ["SELECT color.id,"]


@_DIALECTS
def test_selection_selects_identity_of_relation_owning_computed_values(dialect_name: str) -> None:
    """A relation owning a computed value selects its primary key once more, for the executor to key the value on."""
    lines = plan_sql("{ groups { color { fruitsAggregate { count } } } }", dialect_name)

    assert "color_1.id AS group__color__id" in outer_projection(lines)
