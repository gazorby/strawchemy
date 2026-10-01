"""The selected relations of a level, each planned as a child level and joined to it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strawchemy.dto.strawberry import OrderByEnum
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.transpiler._core.render import order_terms
from strawchemy.transpiler._core.rowset import OrderPriority

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet

__all__ = ("Relations",)


class Relations(PassBase):
    """Plans every selected relation of the level's node, and orders a relation level by its primary keys."""

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        """Adds the joins and projections of the selected relations to ``projection``.

        A relation level without ordering, pagination or DISTINCT ON of its own orders on its primary keys, with
        ``deterministic_ordering``, in its projection: it merges into the parent's, so the child's rows need no
        LATERAL or CTE for it.
        """
        if level.kind == "relation" and level.context.deterministic_ordering and not level.request.orders_rows:
            db_features = level.context.db_features
            terms = [term for key in level.primary_keys() for term in order_terms(key, OrderByEnum.ASC, db_features)]
            projection = projection.with_order_by(OrderPriority.DETERMINISTIC, *terms)
        for child in level.request.selection.children:
            if child.value.is_relation and not child.value.is_computed:
                projection = level.plan_child(child, rows, projection)
        return projection
