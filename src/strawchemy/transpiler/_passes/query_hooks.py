"""The query hooks of a level's node: their statement edits on its rows, their loads in its projection."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Projection, RowSet

__all__ = ("QueryHooks",)


class QueryHooks(PassBase):
    """Runs ``apply_hook`` of each hook of the level's node on its rows, and loads the hooks' columns and relations."""

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        for hook in level.hooks(level.node):
            rows = rows.with_edit(partial(hook.apply_hook, alias=level.alias))
        return rows

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        hooks = level.hooks(level.node)
        return projection.with_hooks(level.node, *hooks) if hooks else projection
