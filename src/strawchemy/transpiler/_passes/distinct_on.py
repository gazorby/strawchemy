"""The DISTINCT ON columns of a level's rows."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from strawchemy.dto.strawberry import QueryNode
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.utils.postgres import comparable

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet

__all__ = ("DistinctOn",)


class DistinctOn(PassBase):
    """Keeps one row per value of the client's DISTINCT ON fields; ``render_rows`` decides native or emulated."""

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        if not level.request.distinct_on:
            return rows
        dialect = level.context.db_features.dialect
        # Wrapped like ``order_terms`` wraps its column, so that render can tell whether the ORDER BY starts with them.
        columns = tuple(
            cast("ColumnElement[Any]", comparable(level.column(QueryNode(value=field.field_definition)), dialect))
            for field in level.request.distinct_on
        )
        return replace(rows, distinct_on=columns)
