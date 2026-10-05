"""The user statement restricting the root rows (``Transpiler(statement=...)``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, inspect, select
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.transpiler._core.rowset import Join, is_where_only

if TYPE_CHECKING:
    from sqlalchemy import Select

    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet

__all__ = ("UserStatement",)


class UserStatement(PassBase):
    """Restricts the root rows to those of the user statement.

    A statement that only adds WHERE clauses to ``select(model)`` has its WHERE copied, dropping its
    ``execution_options``. Any other statement is joined on the primary key, except by DML, which joins nothing.
    """

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        statement = level.context.statement
        if statement is None:
            return rows
        if not is_where_only(statement, select(level.request.model)):
            return rows if level.kind == "dml" else rows.with_join(_primary_key_join(statement, level))
        if statement.whereclause is None:
            return rows
        return rows.with_where(ClauseAdapter(inspect(level.alias).selectable).traverse(statement.whereclause))


def _primary_key_join(statement: Select[Any], level: Level) -> Join:
    """Joins ``statement``, reduced to the primary keys of the level's model, to the level's alias on those keys."""
    pk_attributes = SQLAlchemyInspector.pk_attributes(inspect(level.alias).mapper)
    matched = statement.with_only_columns(*pk_attributes).subquery("user_statement")
    onclause = and_(*[getattr(level.alias, attribute.key) == matched.c[attribute.key] for attribute in pk_attributes])
    return Join(("relation", level.node), matched, onclause, is_outer=False, alias=None)
