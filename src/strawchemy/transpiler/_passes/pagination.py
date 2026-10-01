"""Offset pagination of a level's rows."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet

__all__ = ("OffsetPagination",)


class OffsetPagination(PassBase):
    """Limits a level's rows to the client's page, by limit and offset."""

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        return replace(rows, limit=level.request.limit, offset=level.request.offset)
