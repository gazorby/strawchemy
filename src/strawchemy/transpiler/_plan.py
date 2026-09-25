"""The immutable ``QueryPlan`` describing one SELECT, and ``QueryPlan.emit`` that builds it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import raiseload
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.transpiler._aliasing import require_corresponding_column, same_column

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import Label, Select, SQLColumnExpression
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression
    from sqlalchemy.sql.selectable import Alias

    from strawchemy.repository.typing import OrderBySpec
    from strawchemy.transpiler._query import HookApplier, Join
    from strawchemy.transpiler.hook import ColumnLoadingMode
    from strawchemy.typing import QueryNodeType

__all__ = ("FilterSemiJoin", "HookSpec", "QueryPlan", "add_missing_columns", "distinct_rows")


def add_missing_columns(statement: Select[Any], columns: Sequence[ColumnElement[Any]]) -> Select[Any]:
    """Adds to ``statement`` the ``columns`` it does not already select."""
    return statement.add_columns(
        *[
            column
            for column in columns
            if not any(same_column(column, selected) for selected in statement.selected_columns)
        ]
    )


def distinct_rows(
    statement: Select[Any],
    distinct_on: Sequence[SQLColumnExpression[Any]],
    order_by: Sequence[UnaryExpression[Any]],
    partition_by: Sequence[SQLColumnExpression[Any]] = (),
) -> tuple[Select[Any], ClauseAdapter]:
    """Emulates DISTINCT ON, keeping the first row of each group of ``statement`` by a ``row_number()`` rank.

    Groups are formed on ``partition_by`` then on ``distinct_on``.

    Returns:
        A SELECT of the kept rows, and an adapter mapping the columns of ``statement`` onto it.
    """
    rank = func.row_number().over(partition_by=[*partition_by, *distinct_on], order_by=order_by or None).label(None)
    ranked_statement = add_missing_columns(statement, [expression.element for expression in order_by])
    ranked = ranked_statement.add_columns(rank).subquery()
    ranked_rank = require_corresponding_column(ranked, rank)
    kept_rows = select(*[column for column in ranked.c if column is not ranked_rank]).where(ranked_rank == 1)
    return kept_rows, ClauseAdapter(ranked)


@dataclass(frozen=True)
class HookSpec:
    """Where ``apply_clauses`` runs the query hooks of a node, with which alias and column loading mode."""

    node: QueryNodeType
    alias: AliasedClass[Any]
    loading_mode: ColumnLoadingMode
    export_order_by: bool = False
    """Leaves the hooks' ORDER BY to the plan's ``order_by``, selecting the columns it reads."""


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
    order_keys: tuple[OrderBySpec, ...] = ()
    """Columns and directions of the client ordering, which ``order_by`` is built from."""
    joins: tuple[Join, ...] = ()
    root_aggregation_functions: tuple[Label[Any], ...] = ()
    """Window function columns, selected last."""
    distinct_on: tuple[ColumnElement[Any], ...] = ()
    use_distinct_on: bool = False
    """Use native DISTINCT ON; otherwise the join strategy of the relation emulates it with ``distinct_rows``."""
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
    """Related level owning computed values or collection entities -> its primary-key columns, also selected."""
    collection_entities: Mapping[QueryNodeType, AliasedClass[Any]] = field(default_factory=dict)
    """Relation node loaded apart from its model attribute -> the alias its rows are selected from."""

    def emit(self) -> Select[Any]:
        """Builds the SELECT of this plan."""
        statement = select(self.root)
        if self.collection_entities:
            # A selected LATERAL entity is also a FROM candidate, which makes the left side of its join ambiguous.
            statement = statement.select_from(self.root)
        if self.filter_semijoin is not None:
            statement = statement.join(self.filter_semijoin.alias, onclause=self.filter_semijoin.onclause)
        if self.projection_columns:
            statement = statement.add_columns(*self.projection_columns)
        if self.collection_entities:
            statement = statement.add_columns(*self.collection_entities.values())
        statement = self.apply_clauses(statement)
        return statement.options(raiseload("*"), *self.load_options)

    def apply_clauses(self, statement: Select[Any]) -> Select[Any]:
        """Runs the query hooks, then adds the joins, WHERE, ORDER BY, DISTINCT ON, LIMIT, OFFSET and root aggregations.

        Also used by the join strategies, which build their own selected columns.
        """
        if self.hook_applier is not None:
            for spec in self.hook_specs:
                statement, _ = self.hook_applier.apply(
                    statement,
                    spec.node,
                    spec.alias,
                    spec.loading_mode,
                    in_subquery=True,
                    export_order_by=spec.export_order_by,
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

    @property
    def emulates_distinct_on(self) -> bool:
        """Whether the DISTINCT ON columns must be applied with ``distinct_rows`` rather than natively."""
        return bool(self.distinct_on) and not self.use_distinct_on

    def _apply_distinct(self, statement: Select[Any]) -> Select[Any]:
        """Adds native DISTINCT ON, selecting the ORDER BY columns it requires; does nothing when it is emulated."""
        if not self.use_distinct_on:
            return statement
        statement = add_missing_columns(statement, [expression.element for expression in self.order_by])
        return statement.distinct(*self.distinct_on)
