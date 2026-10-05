"""The selected relations of a level, each planned as a child level and joined to it."""

from __future__ import annotations

from math import prod
from typing import TYPE_CHECKING, Any, cast

from strawchemy.dto.strawberry import OrderByEnum
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.transpiler._core.render import order_terms
from strawchemy.transpiler._core.request import QueryRequest
from strawchemy.transpiler._core.rowset import OrderPriority

if TYPE_CHECKING:
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("Relations",)

_SEPARATE_TOP_N_ROWS = 16


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
        position = {id(child): index for index, child in enumerate(level.request.selection.children)}
        steps: list[tuple[int, tuple[QueryNodeType, ...], bool]] = []
        for group in _sibling_groups(level):
            if _shares(group, level.context.db_features):
                steps.append((position[id(group[0])], group, True))
            else:
                steps.extend((position[id(node)], (node,), False) for node in group)
        for _, nodes, shares in sorted(steps, key=lambda step: step[0]):
            if shares:
                projection = level.plan_siblings(nodes, rows, projection)
            else:
                projection = level.plan_child(nodes[0], rows, projection)
        return projection


def _sibling_groups(level: Level) -> list[tuple[QueryNodeType, ...]]:
    """Groups the selected relations of ``level`` by relationship, in selection order."""
    groups: list[list[QueryNodeType]] = []
    open_groups: dict[Any, list[QueryNodeType]] = {}
    for child in level.request.selection.children:
        if not child.value.is_relation or child.value.is_computed:
            continue
        group = open_groups.get(child.value.model_field)
        if QueryRequest.for_relation(child).distinct_on:
            groups.append([child])
        elif group is None:
            open_groups[child.value.model_field] = group = [child]
            groups.append(group)
        elif list(level.hooks(child)) == list(level.hooks(group[0])):
            group.append(child)
        else:
            groups.append([child])
    return [tuple(group) for group in groups]


def _shares(group: tuple[QueryNodeType, ...], db_features: DatabaseFeatures) -> bool:
    """Tells whether ``group`` is planned as one shared read of its relationship."""
    if len(group) < 2:  # noqa: PLR2004
        return False
    if not db_features.supports_lateral:
        return True
    requests = [QueryRequest.for_relation(node) for node in group]
    if any(request.limit is None for request in requests):
        return True
    return prod((request.offset or 0) + cast("int", request.limit) for request in requests) > _SEPARATE_TOP_N_ROWS
