"""The user statement restricting the root rows (``Transpiler(statement=...)``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, inspect, select, tuple_
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.transpiler._core.pipeline import PassBase
from strawchemy.transpiler._core.rowset import Join, is_where_only

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Select

    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet

__all__ = ("UserStatement",)


class UserStatement(PassBase):
    """Restricts the root rows to those of the user statement.

    A statement only adding WHERE clauses to ``select(model)`` has its WHERE copied, without its ``execution_options``,
    except by DML on databases needing a derived table. Others are joined on the primary key, or matched on it by DML.
    """

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        statement = level.context.statement
        if statement is None:
            return rows
        if not is_where_only(statement, select(level.request.model)):
            if level.kind == "dml":
                return rows.with_where(_primary_key_in(statement, level))
            return rows.with_join(_primary_key_join(statement, level))
        if statement.whereclause is None:
            return rows
        if level.kind == "dml" and level.context.db_features.dml_subquery_needs_derived_table:
            return rows.with_where(_primary_key_in(statement, level))
        return rows.with_where(ClauseAdapter(inspect(level.alias).selectable).traverse(statement.whereclause))


def _primary_key_join(statement: Select[Any], level: Level) -> Join:
    """Joins ``statement``, reduced to the primary keys of the level's model, to the level's alias on those keys."""
    pk_attributes = SQLAlchemyInspector.pk_attributes(inspect(level.alias).mapper)
    matched = statement.with_only_columns(*pk_attributes).subquery("user_statement")
    onclause = and_(*[getattr(level.alias, attribute.key) == matched.c[attribute.key] for attribute in pk_attributes])
    return Join(("relation", level.node), matched, onclause, is_outer=False, alias=None)


def _primary_key_in(statement: Select[Any], level: Level) -> ColumnElement[bool]:
    """Tests that the primary keys of the level's alias are among those of ``statement``."""
    pk_attributes = SQLAlchemyInspector.pk_attributes(inspect(level.alias).mapper)
    # Uncorrelated: the statement reads the UPDATE/DELETE target table, which auto-correlation would drop.
    matched = statement.with_only_columns(*pk_attributes).correlate(None)
    if level.context.db_features.dml_subquery_needs_derived_table:
        derived = matched.subquery("user_statement")
        matched = select(*derived.c)
    outer_pks = [getattr(level.alias, attribute.key) for attribute in pk_attributes]
    if len(outer_pks) == 1:
        return outer_pks[0].in_(matched)
    return tuple_(*outer_pks).in_(matched)
