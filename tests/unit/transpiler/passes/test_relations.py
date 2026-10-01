"""Tests for the ``Relations`` pass: joins of selected relations and the ORDER BY they add to their parent."""

from __future__ import annotations

import re

import pytest

from tests.unit.transpiler.passes.utils import outer_order_by, plan_sql

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
_CTE_DIALECTS = pytest.mark.parametrize("dialect_name", ["sqlite", "mysql"])
_CTE = re.compile(r"\banon_\d+ AS \(")


@_DIALECTS
def test_relations_nested_joined_flat(dialect_name: str) -> None:
    """A selected relation without ordering or pagination of its own is one plain LEFT OUTER JOIN."""
    lines = plan_sql("{ colors { fruits { name } } }", dialect_name)

    assert [line.strip() for line in lines if "JOIN" in line] == ["LEFT OUTER JOIN fruit AS fruit_1"]
    assert not any("LATERAL" in line or "WITH" in line for line in lines)


@_DIALECTS
def test_relations_order_parent_by_child_keys(dialect_name: str) -> None:
    """With deterministic ordering, a relation without ordering of its own orders the parent query by its keys."""
    lines = plan_sql("{ colors { fruits { name } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "fruit_1.id ASC"]


@_DIALECTS
def test_relations_order_outer_keys_before_nested_keys(dialect_name: str) -> None:
    """With deterministic ordering, each relation level's keys come after those of the level above it."""
    lines = plan_sql("{ colors { fruits { color { name } } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "fruit_1.id ASC", "color_1.id ASC"]


@_DIALECTS
def test_relations_own_order_comes_before_nested_keys(dialect_name: str) -> None:
    """A relation's own ordering, carried by its LATERAL or CTE, orders the query before the relations below it."""
    lines = plan_sql("{ colors { fruits(orderBy: { name: ASC }) { color { name } } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "anon_1.name ASC", "color_1.id ASC"]


@_DIALECTS
def test_relations_own_limit_uses_lateral_or_cte(dialect_name: str) -> None:
    """A relation with its own limit is a LATERAL join on postgresql, a CTE ranked by ``dense_rank`` otherwise."""
    sql = "\n".join(plan_sql("{ colorsPaginatedFruits { fruits(limit: 2) { name } } }", dialect_name))

    if dialect_name == "postgresql":
        assert "LEFT OUTER JOIN LATERAL" in sql
        assert "LIMIT" in sql
    else:
        assert sql.startswith("WITH")
        assert "dense_rank()" in sql
        assert "LATERAL" not in sql


@_DIALECTS
def test_same_model_two_paths_gets_two_aliases(dialect_name: str) -> None:
    """A model reached from the root and through a relation is read from two aliases, correlated differently."""
    lines = plan_sql("{ colors { fruits { color { name } } } }", dialect_name)

    assert "  FROM color AS color" in lines
    assert [line.strip() for line in lines if "JOIN" in line] == [
        "LEFT OUTER JOIN fruit AS fruit_1",
        "LEFT OUTER JOIN color AS color_1",
    ]


@_CTE_DIALECTS
def test_aliases_differing_in_limit_share_one_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, aliases of a relation differing only in limit join one rank CTE, each with its own bounds."""
    lines = plan_sql(
        "{ colorsPaginatedFruits { a: fruits(limit: 2) { name } b: fruits(limit: 3) { name } } }", dialect_name
    )
    sql = "\n".join(lines).replace("`", "")

    assert len(_CTE.findall(sql)) == 1
    assert [line.strip() for line in lines if "JOIN" in line] == [
        "LEFT OUTER JOIN anon_1",
        "LEFT OUTER JOIN anon_1 AS anon_2",
    ]
    assert "AND anon_1.rank <=" in sql
    assert "AND anon_2.rank <=" in sql


@_CTE_DIALECTS
@pytest.mark.allow_duplicate_reads(reason="aliases a and b of colors.fruits, ordered differently, read fruit twice")
def test_ctes_with_different_bodies_are_not_shared(dialect_name: str) -> None:
    """Without LATERAL, aliases of a relation ordered differently keep one rank CTE each."""
    lines = plan_sql(
        "{ colors { a: fruits(orderBy: { name: ASC }) { name } b: fruits(orderBy: { name: DESC }) { name } } }",
        dialect_name,
    )

    assert len(_CTE.findall("\n".join(lines))) == 2
    assert [line.strip() for line in lines if "JOIN" in line] == ["LEFT OUTER JOIN anon_1", "LEFT OUTER JOIN anon_2"]
