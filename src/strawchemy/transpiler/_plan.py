"""The immutable ``QueryPlan`` describing one SELECT, and ``QueryPlan.emit`` that builds it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import raiseload

from strawchemy.transpiler._aliasing import same_column

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import Label, Select
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression
    from sqlalchemy.sql.selectable import Alias

    from strawchemy.transpiler._query import HookApplier, Join
    from strawchemy.transpiler.hook import ColumnLoadingMode
    from strawchemy.typing import QueryNodeType

__all__ = ("FilterSemiJoin", "HookSpec", "QueryPlan", "add_missing_columns")


def add_missing_columns(statement: Select[Any], columns: Sequence[ColumnElement[Any]]) -> Select[Any]:
    """Adds to ``statement`` the ``columns`` it does not already select."""
    return statement.add_columns(
        *[
            column
            for column in columns
            if not any(same_column(column, selected) for selected in statement.selected_columns)
        ]
    )


@dataclass(frozen=True)
class HookSpec:
    """Where ``apply_clauses`` runs the query hooks of a node, with which alias and column loading mode."""

    node: QueryNodeType
    alias: AliasedClass[Any]
    loading_mode: ColumnLoadingMode


@dataclass(frozen=True)
class FilterSemiJoin:
    """Join from the root alias to the user filter statement, on the primary key."""

    alias: Alias
    onclause: ColumnElement[bool]


@dataclass(frozen=True)
class QueryPlan:
    """Everything needed to build one SELECT; the planner makes every decision, ``emit`` only assembles."""

    root: AliasedClass[Any]
    filter_semijoin: FilterSemiJoin | None
    projection_columns: tuple[ColumnElement[Any], ...] = ()
    """Columns selected besides the root model, in selection order."""
    load_options: tuple[_AbstractLoad, ...] = ()
    where: tuple[ColumnElement[bool], ...] = ()
    order_by: tuple[UnaryExpression[Any], ...] = ()
    joins: tuple[Join, ...] = ()
    root_aggregation_functions: tuple[Label[Any], ...] = ()
    """Window function columns, selected last."""
    distinct_on: tuple[ColumnElement[Any], ...] = ()
    use_distinct_on: bool = False
    """Use native DISTINCT ON; otherwise it was emulated in the pagination subquery."""
    limit: int | None = None
    offset: int | None = None
    hook_specs: tuple[HookSpec, ...] = ()
    hook_applier: HookApplier | None = None
    """Runs the query hooks, whose ``apply_hook`` is user code that cannot be stored as plan data."""
    column_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Computed, transform and root aggregation node -> the column holding its value.

    The executor reads values by column object, so column names do not matter.
    """
    identity_columns: Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]] = field(default_factory=dict)
    """Related level owning computed values -> its primary-key columns, also in ``projection_columns``."""

    def emit(self) -> Select[Any]:
        """Builds the SELECT of this plan."""
        statement = select(self.root)
        if self.filter_semijoin is not None:
            statement = statement.join(self.filter_semijoin.alias, onclause=self.filter_semijoin.onclause)
        if self.projection_columns:
            statement = statement.add_columns(*self.projection_columns)
        statement = self.apply_clauses(statement)
        return statement.options(raiseload("*"), *self.load_options)

    def apply_clauses(self, statement: Select[Any]) -> Select[Any]:
        """Runs the query hooks, then adds the joins, WHERE, ORDER BY, DISTINCT ON, LIMIT, OFFSET and root aggregations.

        Also used by the join strategies, which build their own selected columns.
        """
        if self.hook_applier is not None:
            for spec in self.hook_specs:
                statement, _ = self.hook_applier.apply(
                    statement, spec.node, spec.alias, spec.loading_mode, in_subquery=True
                )
        for join in sorted(self.joins):
            statement = statement.join(join.target, onclause=join.onclause, isouter=join.is_outer)
        if self.where:
            statement = statement.where(*self.where)
        if self.order_by:
            statement = statement.order_by(*self.order_by)
        if self.distinct_on:
            statement = self._apply_distinct(statement)
        if self.limit is not None:
            statement = statement.limit(self.limit)
        if self.offset is not None:
            statement = statement.offset(self.offset)
        if self.root_aggregation_functions:
            statement = statement.add_columns(*self.root_aggregation_functions)
        return statement

    def _apply_distinct(self, statement: Select[Any]) -> Select[Any]:
        """Adds native DISTINCT ON, selecting the ORDER BY columns it requires.

        Does nothing when DISTINCT ON is emulated: the subquery and a ``rank = 1`` predicate in ``where`` handle it.
        """
        if not self.use_distinct_on:
            return statement
        statement = add_missing_columns(statement, [expression.element for expression in self.order_by])
        return statement.distinct(*self.distinct_on)
