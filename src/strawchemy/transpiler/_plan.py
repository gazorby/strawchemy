"""Explicit query-plan IR and its emitter.

This module introduces the immutable ``QueryPlan`` and the pure ``emit_plan`` function.
Covers a root ``SELECT`` with projection, an optional filter semi-join, relation joins
(LATERAL/CTE), WHERE, ORDER BY, DISTINCT ON, LIMIT/OFFSET, and root aggregation window
columns. Structure is held as data; leaf predicate/column/order expressions are opaque
SQLAlchemy fragments.

Classes:
    FilterSemiJoin: A pre-built PK semi-join to the filter-statement subquery.
    QueryPlan: The immutable plan for a supported-shape query.

Functions:
    emit_plan: Emits a SQLAlchemy Select from a QueryPlan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import raiseload

if TYPE_CHECKING:
    from sqlalchemy import Label, Select
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression
    from sqlalchemy.sql.selectable import Alias

    from strawchemy.transpiler._query import HookApplier, Join
    from strawchemy.transpiler.hook import ColumnLoadingMode
    from strawchemy.typing import QueryNodeType

__all__ = ("FilterSemiJoin", "HookSpec", "QueryPlan", "emit_plan")


@dataclass(frozen=True)
class HookSpec:
    """A recorded outer query-hook application point, replayed by the emitter.

    Attributes:
        node: The query node whose registered hooks apply.
        alias: The aliased entity passed to the hooks.
        loading_mode: The column loading mode ("undefer" for outer hooks).
    """

    node: QueryNodeType
    alias: AliasedClass[Any]
    loading_mode: ColumnLoadingMode


@dataclass(frozen=True)
class FilterSemiJoin:
    """A pre-built primary-key semi-join to the filter-statement subquery.

    Attributes:
        alias: The filter subquery aliased to its primary-key columns.
        onclause: The PK-equality predicate joining the root alias to the subquery.
    """

    alias: Alias
    onclause: ColumnElement[bool]


@dataclass(frozen=True)
class QueryPlan:
    """Immutable plan for a leaf-shaped SELECT (root + WHERE + ORDER BY).

    Structure is data; leaf expressions are opaque SQLAlchemy fragments.

    Attributes:
        root: The FROM-clause root alias.
        filter_semijoin: The PK semi-join to the filter statement, or None.
        projection_columns: Extra columns added to the projection in selection order
            (JSON/column transforms and aggregation function columns).
        load_options: ORM loader options (``load_only`` etc.) excluding ``raiseload``.
        where: The boolean filter predicates.
        order_by: The built ORDER BY expressions.
        joins: Relation joins to apply, ordered by depth at emit time.
        root_aggregation_functions: Window aggregation columns added last to the projection.
        distinct_on: DISTINCT ON expressions (empty when no distinct).
        use_distinct_on: Whether native DISTINCT ON applies (False ⇒ rank-emulation in subquery).
        limit: Outer LIMIT, or None.
        offset: Outer OFFSET, or None.
        hook_specs: Outer query-hook application points, replayed by the emitter.
        hook_applier: Applies the registered hooks; carried because apply_hook is arbitrary
            statement-mutating code that cannot be captured as plan data. None when no hooks.
    """

    root: AliasedClass[Any]
    filter_semijoin: FilterSemiJoin | None
    projection_columns: tuple[ColumnElement[Any], ...]
    load_options: tuple[_AbstractLoad, ...]
    where: tuple[ColumnElement[bool], ...]
    order_by: tuple[UnaryExpression[Any], ...]
    joins: tuple[Join, ...] = ()
    root_aggregation_functions: tuple[Label[Any], ...] = ()
    distinct_on: tuple[ColumnElement[Any], ...] = ()
    use_distinct_on: bool = False
    limit: int | None = None
    offset: int | None = None
    hook_specs: tuple[HookSpec, ...] = ()
    hook_applier: HookApplier | None = None


def _apply_distinct(statement: Select[Any], plan: QueryPlan) -> Select[Any]:
    """Mirrors Query._distinct_on: native DISTINCT ON only.

    When ``use_distinct_on`` is False the distinctness is handled inside the subquery
    (row_number rank + an outer ``WHERE rank = 1`` already present in ``plan.where``), so
    this is a no-op. When True, ORDER BY columns absent from the SELECT list are added
    (DISTINCT ON requires them) before applying ``.distinct(*distinct_on)``.

    Args:
        statement: The statement being assembled.
        plan: The query plan (provides ``order_by``, ``distinct_on``, ``use_distinct_on``).

    Returns:
        The statement with DISTINCT ON applied, or unchanged.
    """
    if not plan.use_distinct_on:
        return statement
    statement = statement.add_columns(
        *[
            expression.element
            for expression in plan.order_by
            if not any(selected.compare(expression.element) for selected in statement.selected_columns)
        ]
    )
    return statement.distinct(*plan.distinct_on)


def emit_plan(plan: QueryPlan) -> Select[Any]:
    """Emits the SQLAlchemy Select for a query plan.

    Mechanical assembly only; all decisions live in the planner.

    Args:
        plan: The query plan to emit.

    Returns:
        The assembled SQLAlchemy Select statement.
    """
    statement = select(plan.root)
    if plan.filter_semijoin is not None:
        statement = statement.join(plan.filter_semijoin.alias, onclause=plan.filter_semijoin.onclause)
    if plan.projection_columns:
        statement = statement.add_columns(*plan.projection_columns)
    if plan.hook_applier is not None:
        for spec in plan.hook_specs:
            statement = plan.hook_applier.apply_statement_hooks(statement, spec.node, spec.alias)
    for join in sorted(plan.joins):
        statement = statement.join(join.target, onclause=join.onclause, isouter=join.is_outer)
    if plan.where:
        statement = statement.where(*plan.where)
    if plan.order_by:
        statement = statement.order_by(*plan.order_by)
    if plan.distinct_on:
        statement = _apply_distinct(statement, plan)
    if plan.limit is not None:
        statement = statement.limit(plan.limit)
    if plan.offset is not None:
        statement = statement.offset(plan.offset)
    if plan.root_aggregation_functions:
        statement = statement.add_columns(*plan.root_aggregation_functions)
    return statement.options(raiseload("*"), *plan.load_options)
