"""Tests for the transpiler's function-node collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from strawchemy.transpiler._scope import FunctionNodeCollector

if TYPE_CHECKING:
    from strawchemy.typing import QueryNodeType


def _node(name: str) -> QueryNodeType:
    """Return a hashable sentinel standing in for a query node."""
    return cast("QueryNodeType", name)


def test_referenced_combines_where_selection_and_order() -> None:
    """Referenced nodes = (where & selection) | order_by, matching prior scope logic."""
    collector = FunctionNodeCollector()
    collector.selection.update({_node("a"), _node("b")})
    collector.where.update({_node("b"), _node("c")})
    collector.order_by.update({_node("d")})
    assert collector.referenced == {_node("b"), _node("d")}
