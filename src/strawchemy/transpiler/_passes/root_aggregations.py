"""The aggregations of a whole query, computed next to its rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strawchemy.transpiler._core import functions
from strawchemy.transpiler._core.functions import AggregateFunction
from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet

__all__ = ("RootAggregations",)


class RootAggregations(PassBase):
    """Selects each root aggregation as a window function over the level's rows, after their pagination."""

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        if (tree := level.request.root_aggregation_tree) is None:
            return projection
        dialect = level.context.db_features.dialect
        for function_node in tree.children:
            for function in AggregateFunction.for_selection(function_node):
                label = functions.build(function, level.alias, dialect, over=True)
                projection = projection.with_root_aggregation(function.node, label)
        return projection
