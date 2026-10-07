"""The only SQL builder of the transpiler: ``render_rows`` for subqueries, ``render_plan`` for the final SELECT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Cast, func, null, select
from sqlalchemy.orm import Load, load_only, raiseload
from sqlalchemy.sql.elements import UnaryExpression, _anonymous_label
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.dto.strawberry import OrderByEnum
from strawchemy.exceptions import TranspilingError
from strawchemy.utils.postgres import comparable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import Select, SQLColumnExpression
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, FromClause
    from sqlalchemy.sql.elements import KeyedColumnElement

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._core.plan import QueryPlan
    from strawchemy.transpiler._core.rowset import Join, OrderPriority, Projection, RowSet, StatementEdit
    from strawchemy.transpiler.hook import QueryHook

__all__ = (
    "RenderedRows",
    "adapt_clauses",
    "add_missing_columns",
    "clause_element",
    "distinct_rows",
    "order_terms",
    "ordered_column",
    "priority_sorted",
    "render_plan",
    "render_rows",
    "require_corresponding_column",
    "same_column",
)


@dataclass(frozen=True)
class RenderedRows:
    """The SELECT of a ``RowSet`` and its final ORDER BY terms, for callers that re-apply them outside."""

    statement: Select[Any]
    order_by: tuple[UnaryExpression[Any], ...]


def _by_depth(joins: Mapping[Any, Join]) -> list[Join]:
    return sorted(joins.values(), key=lambda join: join.key[1].level)


def _assemble(
    statement: Select[Any],
    *,
    rows: RowSet,
    joins: Sequence[Join],
    where: Sequence[ColumnElement[bool]],
    order_by: Sequence[UnaryExpression[Any]],
    db_features: DatabaseFeatures,
    distinct_on: Sequence[ColumnElement[Any]] = (),
    partition_by: Sequence[ColumnElement[Any]] = (),
    select_order_columns: bool = False,
) -> tuple[Select[Any], tuple[UnaryExpression[Any], ...]]:
    """Adds edits, joins, WHERE, ORDER BY, DISTINCT ON, LIMIT and OFFSET to ``statement``, in that order.

    The ORDER BY an edit adds goes before ``order_by``.

    Returns:
        The statement, and its final ORDER BY terms.
    """
    statement, edit_order_by = _run_edits(statement, rows.edits)
    for join in joins:
        if join.left is None:
            statement = statement.join(join.target, onclause=join.onclause, isouter=join.is_outer)
        else:
            statement = statement.join_from(join.left, join.target, onclause=join.onclause, isouter=join.is_outer)
    if where:
        statement = statement.where(*where)
    terms = (*edit_order_by, *order_by)
    if not distinct_on:
        if select_order_columns:
            statement = add_missing_columns(statement, [ordered_column(term) for term in terms])
    elif _is_native_distinct(distinct_on, terms, db_features):
        statement = add_missing_columns(statement, [ordered_column(term) for term in terms]).distinct(*distinct_on)
    else:
        statement, adapter = distinct_rows(statement, distinct_on, terms, partition_by)
        terms = tuple(adapter.traverse(term) for term in terms)
    if terms:
        statement = statement.order_by(*terms)
    if rows.limit is not None:
        statement = statement.limit(rows.limit)
    if rows.offset is not None:
        statement = statement.offset(rows.offset)
    return statement, terms


def _run_edits(
    statement: Select[Any], edits: Iterable[StatementEdit]
) -> tuple[Select[Any], tuple[UnaryExpression[Any], ...]]:
    for edit in edits:
        statement = edit(statement)
    order_by = tuple(
        clause if isinstance(clause, UnaryExpression) else clause.asc()
        for clause in statement._order_by_clauses  # noqa: SLF001
    )
    return statement.order_by(None), order_by


def _is_native_distinct(
    distinct_on: Sequence[ColumnElement[Any]], order_by: Sequence[UnaryExpression[Any]], db_features: DatabaseFeatures
) -> bool:
    """Tells whether DISTINCT ON can be native: supported, and the ORDER BY starts with the DISTINCT ON columns."""
    if not db_features.supports_distinct_on:
        return False
    if not order_by:
        return True
    if len(order_by) < len(distinct_on):
        return False
    return all(
        same_column(clause_element(ordered_column(term)), clause_element(column))
        for term, column in zip(order_by, distinct_on, strict=False)
    )


def _loader_options(projection: Projection) -> list[_AbstractLoad]:
    """Builds ``load_only`` and hook loader options per entity, for all its nodes; the root's are top-level."""
    aliases: dict[int, AliasedClass[Any]] = {}
    loaded: dict[int, list[str] | None] = {}
    hooks: dict[int, list[QueryHook[Any]]] = {}
    for node, alias in projection.entities.items():
        key = id(alias)
        aliases.setdefault(key, alias)
        node_keys = projection.loaded.get(node)
        if (keys := loaded.setdefault(key, [])) is not None:
            # A node loading no explicit keys loads every column, and so does its entity.
            loaded[key] = [*keys, *(name for name in node_keys if name not in keys)] if node_keys else None
        alias_hooks = hooks.setdefault(key, [])
        alias_hooks.extend(hook for hook in projection.hooks.get(node, ()) if all(hook is not h for h in alias_hooks))
    options: list[_AbstractLoad] = []
    for index, (key, alias) in enumerate(aliases.items()):
        alias_options: list[_AbstractLoad] = []
        if keys := loaded[key]:
            alias_options.append(load_only(*[getattr(alias, name) for name in keys]))
        for hook in hooks[key]:
            alias_options.extend(hook.column_load_options(alias))
            alias_options.extend(hook.load_relationships(alias))
        if index == 0:
            options.extend(alias_options)
        elif alias_options:
            options.append(Load(alias).options(*alias_options))
    return options


def clause_element(column: ColumnElement[Any] | QueryableAttribute[Any]) -> ColumnElement[Any]:
    return column.__clause_element__() if hasattr(column, "__clause_element__") else column


def order_terms(
    column: ColumnElement[Any], direction: OrderByEnum, db_features: DatabaseFeatures
) -> tuple[UnaryExpression[Any], ...]:
    """Builds the ORDER BY terms of one column.

    Without native ``NULLS FIRST``/``NULLS LAST``, null placement orders on ``column IS NULL`` first.
    """
    column = cast("ColumnElement[Any]", comparable(column, db_features.dialect))
    native = db_features.supports_null_ordering
    ascending = direction in {OrderByEnum.ASC, OrderByEnum.ASC_NULLS_FIRST, OrderByEnum.ASC_NULLS_LAST}
    ordered = column.asc() if ascending else column.desc()
    if direction in {OrderByEnum.ASC, OrderByEnum.DESC}:
        return (ordered,)
    nulls_first = direction in {OrderByEnum.ASC_NULLS_FIRST, OrderByEnum.DESC_NULLS_FIRST}
    if native:
        return ((ordered.nulls_first() if nulls_first else ordered.nulls_last()),)
    is_null = column.is_(null())
    return ((is_null.desc() if nulls_first else is_null.asc()), ordered)


def ordered_column(term: UnaryExpression[Any]) -> ColumnElement[Any]:
    """Returns the expression ``term`` orders, without its ASC, DESC and NULLS modifiers."""
    expression: Any = term
    while isinstance(expression, UnaryExpression) and expression.modifier is not None:
        expression = expression.element
    return expression


def add_missing_columns(statement: Select[Any], columns: Sequence[ColumnElement[Any]]) -> Select[Any]:
    """Adds to ``statement`` the ``columns`` it does not select; a CAST adds its operand, whose name it takes."""
    for column in (column.clause if isinstance(column, Cast) else column for column in columns):
        if not any(same_column(column, selected) for selected in statement.selected_columns):
            statement = statement.add_columns(column)
    return statement


def adapt_clauses(clauses: Sequence[UnaryExpression[Any]], selectable: FromClause) -> tuple[UnaryExpression[Any], ...]:
    adapter = ClauseAdapter(selectable)
    return tuple(adapter.traverse(clause) for clause in clauses)


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
    ranked_statement = add_missing_columns(statement, [ordered_column(expression) for expression in order_by])
    ranked = ranked_statement.add_columns(rank).subquery()
    ranked_rank = require_corresponding_column(ranked, rank)
    kept_rows = cast(
        "Select[Any]", select(*[column for column in ranked.c if column is not ranked_rank]).where(ranked_rank == 1)
    )
    return kept_rows, ClauseAdapter(ranked)


def priority_sorted(
    order_by: Iterable[tuple[OrderPriority, UnaryExpression[Any]]],
) -> list[tuple[OrderPriority, UnaryExpression[Any]]]:
    return sorted(order_by, key=lambda item: item[0])


def render_rows(
    rows: RowSet,
    columns: Sequence[ColumnElement[Any]],
    db_features: DatabaseFeatures,
    partition_by: Sequence[ColumnElement[Any]] = (),
) -> RenderedRows:
    """Builds the SELECT of ``columns`` over ``rows``, the body of a subquery, LATERAL, CTE or EXISTS.

    Clauses are added in a fixed order: edits, joins by node depth, WHERE, ORDER BY, DISTINCT ON, LIMIT, OFFSET.
    The columns the ORDER BY reads are selected, so that it can be adapted onto a wrapper of the statement.
    """
    statement, order_by = _assemble(
        cast("Select[Any]", select(*columns).select_from(rows.source)),
        rows=rows,
        joins=_by_depth(rows.joins),
        where=rows.where,
        order_by=[term for _, term in priority_sorted(rows.order_by)],
        distinct_on=rows.distinct_on,
        db_features=db_features,
        partition_by=partition_by,
        select_order_columns=True,
    )
    return RenderedRows(statement, order_by)


def render_plan(plan: QueryPlan) -> Select[Any]:
    """Builds the final SELECT: entities, projection columns, joins of both stages, loader options, ``raiseload``."""
    rows, projection, db_features = plan.rows, plan.projection, plan.context.db_features
    # The executor reads relation entities by position, and columns selected from a LATERAL make it a FROM candidate,
    # so the left side of the joins must be explicit.
    entities = list({id(alias): alias for alias in projection.entities.values()}.values())
    statement = select(*entities).select_from(rows.source).add_columns(*projection.columns)
    ranks = {id(page.rank): page.rank for page in projection.pages.values()}
    statement = statement.add_columns(
        *[rank for rank in ranks.values() if all(rank is not column for column in projection.columns)]
    )
    if rows.distinct_on:
        msg = "rows with DISTINCT ON must be wrapped before rendering the plan"
        raise TranspilingError(msg)
    statement, _ = _assemble(
        statement,
        rows=rows,
        joins=[*_by_depth(rows.joins), *_by_depth(projection.joins)],
        where=rows.where,
        order_by=[term for _, term in (*priority_sorted(rows.order_by), *projection.order_by)],
        db_features=db_features,
    )
    if projection.root_aggregations:
        statement = statement.add_columns(*projection.root_aggregations)
    return statement.options(raiseload("*"), *_loader_options(projection))


def require_corresponding_column(selectable: FromClause, label: KeyedColumnElement[Any]) -> KeyedColumnElement[Any]:
    """Finds the column of ``selectable`` that exposes ``label``, matched by object rather than by name.

    The column is not labelled again: a label on an anonymous column gets a name that changes between runs, and the
    executor reads values by column object anyway.

    Raises:
        TranspilingError: If ``selectable`` does not expose ``label``.
    """
    column = selectable.corresponding_column(label)
    if column is None:  # pragma: no cover  # defensive
        msg = f"column {label!r} not exported by {selectable!r}"
        raise TranspilingError(msg)
    return column


def same_column(left: ColumnElement[Any], right: ColumnElement[Any]) -> bool:
    """Tells whether two columns are the same expression over the same FROM.

    ``compare()`` ignores the generated name of an anonymous label and of an anonymous alias, so both are told apart by
    object: labels compare by identity, columns also need the same table.
    """
    if left is right:
        return True
    if any(isinstance(getattr(column, "name", None), _anonymous_label) for column in (left, right)):
        return False
    return getattr(left, "table", None) is getattr(right, "table", None) and left.compare(right)
