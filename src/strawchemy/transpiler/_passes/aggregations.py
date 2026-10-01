"""The aggregates a level selects on its relations, read from the join that already computes them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet

__all__ = ("Aggregations",)


class Aggregations(PassBase):
    """Selects the requested functions of each aggregation of the level's node; the join may compute more."""

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        request = level.request
        for child in request.selection.children:
            if not child.value.is_aggregate:
                continue
            selected = request.selected_functions(child)
            for function_node, function in request.aggregate_functions(child).items():
                if function_node in selected:
                    column, projection = level.projected_aggregate(function, rows, projection)
                    projection = projection.with_computed(function_node, column)
        return projection
