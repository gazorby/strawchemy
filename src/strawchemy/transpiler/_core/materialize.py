"""The only subquery decision: inlining a level's rows next to its projection, or rendering them as one FROM."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import FromClause, inspect, select
from sqlalchemy.orm import RelationshipProperty, aliased
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.util import ClauseAdapter, surface_selectables

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.transpiler._core.attach import attach_rows, attach_shared_rows
from strawchemy.transpiler._core.plan import QueryPlan
from strawchemy.transpiler._core.render import (
    adapt_clauses,
    clause_element,
    render_rows,
    require_corresponding_column,
    same_column,
)
from strawchemy.transpiler._core.rewrite import PlanRewriter
from strawchemy.transpiler._core.rowset import OrderPriority, Projection, RowSet
from strawchemy.transpiler._core.share import share_ctes

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from sqlalchemy import ClauseElement, Label, Select
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.visitors import ExternallyTraversible

    from strawchemy.transpiler._core.attach import RankWindow
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import Join
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import QueryNodeType

__all__ = ("materialize", "materialize_shared")


class _Rebase(PlanRewriter):
    """Moves a projection from the FROM clauses of its rows onto ``selectable``, which renders those rows and exports them.

    A projection-stage LATERAL correlated to the rows is rewritten too, and every column read from it moves to the
    rewritten one.
    """

    def __init__(
        self, selectable: FromClause, rows: RowSet, entities: Mapping[AliasedClass[Any], AliasedClass[Any]]
    ) -> None:
        super().__init__()
        self._row_from_clauses = _row_from_clauses(rows)
        # Only row-stage columns are adapted: another alias of a row-stage table would match its columns too.
        self._adapter = ClauseAdapter(
            selectable, include_fn=lambda element: not _reads_other(element, self._row_from_clauses)
        )
        self._entities = dict(entities)
        self._targets: dict[FromClause, FromClause] = {}

    def _replace(self, element: ExternallyTraversible, **_: object) -> ExternallyTraversible | None:
        if isinstance(element, FromClause) and element in self._targets:
            return self._targets[element]
        if isinstance(element, ColumnClause) and element.table in self._targets:
            return self._targets[element.table].corresponding_column(element)
        return self._adapter.replace(element)

    def _entity(self, alias: AliasedClass[Any]) -> AliasedClass[Any]:
        """Returns the entity replacing ``alias``, built over the rewritten target of its selectable if there is one."""
        if alias not in self._entities and (target := self._targets.get(inspect(alias).selectable)) is not None:
            self._entities[alias] = aliased(alias, target)
        return self._entities.get(alias, alias)

    def _target(self, target: FromClause | AliasedClass[Any]) -> FromClause | AliasedClass[Any]:
        if isinstance(target, FromClause) and _reads(target, {*self._row_from_clauses, *self._targets}):
            rewritten = self._expression(target)
            self._targets[target] = rewritten
            return rewritten
        return target


def _inlines(level: Level, rows: RowSet, projection: Projection) -> bool:
    """Tells whether ``rows`` can share the FROM of the projection; a relation's must fit in a plain join."""
    if level.kind == "root":
        return (
            rows.limit is None
            and rows.offset is None
            and not rows.distinct_on
            and not rows.edits_shape_rows()
            and not _repeats_aggregated_rows(projection)
        )
    relationship = level.node.value.model_field.property if level.kind == "relation" else None
    to_one = isinstance(relationship, RelationshipProperty) and not relationship.uselist
    if not rows.only_filters(unordered=to_one):
        return False
    return level.kind != "relation" or not (rows.order_by or rows.joins)


def _materialize(level: Level, rows: RowSet, projection: Projection) -> QueryPlan:
    if level.kind in {"exists", "dml"} or _inlines(level, rows, projection):
        return QueryPlan(rows, projection, level.context)
    row_aliases = _row_aliases(rows)
    exported = _read_columns(projection, rows, row_aliases)
    exported.extend(column for column in rows.distinct_on if not any(same_column(column, read) for read in exported))
    db_features = level.context.db_features
    if level.kind == "relation":
        assert level.parent is not None
        join, order_by = attach_rows(
            rows,
            level.node,
            exported,
            level.node.value.model_field,
            level.parent.alias,
            db_features,
            is_outer=True,
        )
        join, projection = _rebased(join, rows, projection, row_aliases)
        # This level's own ordering goes before that of the relations below it, already in the projection.
        own_order_by = tuple((OrderPriority.CLIENT, term) for term in order_by)
        projection = replace(projection, order_by=(*own_order_by, *projection.order_by))
        assert join.alias is not None
        return QueryPlan(RowSet.over(join.alias), projection, level.context, join_to_parent=join)
    rendered = render_rows(rows, exported, db_features)
    statement, aggregations = rendered.statement, {}
    if _repeats_aggregated_rows(projection):
        statement, projection, aggregations = _aggregated_rows(statement, projection)
    page = statement.subquery(level.request.model.__tablename__)
    entities = _entities_over(page, row_aliases)
    page_rows = RowSet.over(entities[rows.source]).with_order_by(
        OrderPriority.CLIENT, *adapt_clauses(rendered.order_by, page)
    )
    projection = _Rebase(page, rows, entities).projection(projection)
    for node, column in aggregations.items():
        projection = projection.with_root_aggregation(node, require_corresponding_column(page, column))
    return QueryPlan(page_rows, projection, level.context)


def _repeats_aggregated_rows(projection: Projection) -> bool:
    """Tells whether ``projection`` has root aggregations and joins a to-many relation, which repeats the root rows."""
    return bool(projection.root_aggregations) and any(
        key[0] == "relation" and key[1].value.uselist for key in projection.joins
    )


def _aggregated_rows(
    statement: Select[Any], projection: Projection
) -> tuple[Select[Any], Projection, dict[QueryNodeType, Label[Any]]]:
    """Selects the root aggregations of ``projection`` over the rows of ``statement``, before any join repeats them.

    Returns:
        The statement, ``projection`` without its root aggregations, and the column of each one in the statement.
    """
    rows = statement.subquery()
    adapter = ClauseAdapter(rows)
    columns = {id(column): cast("Label[Any]", adapter.traverse(column)) for column in projection.root_aggregations}
    column_map = {node: column for node, column in projection.column_map.items() if id(column) not in columns}
    aggregations = {
        node: columns[id(column)] for node, column in projection.column_map.items() if id(column) in columns
    }
    statement = cast("Select[Any]", select(*rows.c, *columns.values()))
    return statement, replace(projection, root_aggregations=(), column_map=column_map), aggregations


def _rebased(
    join: Join, rows: RowSet, projection: Projection, row_aliases: Sequence[AliasedClass[Any]]
) -> tuple[Join, Projection]:
    """Moves ``projection`` onto the target of ``join``, which renders ``rows``, and gives ``join`` its entity."""
    assert join.alias is not None
    entities = _entities_over(_selectable(join.target), row_aliases, {rows.source: join.alias})
    join = replace(join, alias=entities[rows.source])
    return join, _Rebase(_selectable(join.target), rows, entities).projection(projection)


def _row_aliases(rows: RowSet) -> list[AliasedClass[Any]]:
    """Returns the entity aliases the rows are read from: their source, then each relation join's."""
    return [
        rows.source,
        *(join.alias for join in rows.joins.values() if join.key[0] == "relation" and join.alias is not None),
    ]


def _selectable(from_: FromClause | AliasedClass[Any]) -> FromClause:
    return inspect(from_).selectable if isinstance(from_, AliasedClass) else from_


def _row_from_clauses(rows: RowSet) -> set[FromClause]:
    """Returns every FROM the rows read columns from: aliases, and the LATERAL or CTE of aggregate joins."""
    from_clauses = [*map(_selectable, _row_aliases(rows)), *(_selectable(join.target) for join in rows.joins.values())]
    return {surface for from_ in from_clauses for surface in surface_selectables(from_)}


def _reads(clause: ClauseElement, from_clauses: Collection[FromClause]) -> bool:
    return any(
        isinstance(element, ColumnClause) and element.table in from_clauses for element in visitors.iterate(clause)
    )


def _reads_other(element: ClauseElement, from_clauses: Collection[FromClause]) -> bool:
    """Tells whether ``element`` is a column of a FROM that is not one of ``from_clauses``."""
    return isinstance(element, ColumnClause) and element.table is not None and element.table not in from_clauses


def _entity_reads(alias: AliasedClass[Any], loaded: Sequence[str] | None, hooks: Sequence[QueryHook[Any]]) -> list[Any]:
    """Returns the attributes an entity loads: ``loaded`` or every undeferred column, its keys, its hooks' columns."""
    mapper = inspect(alias).mapper
    keys = loaded if loaded is not None else [prop.key for prop in mapper.column_attrs if not prop.deferred]
    reads: list[Any] = [getattr(alias, key) for key in keys]
    reads.extend(getattr(alias, attribute.key) for attribute in SQLAlchemyInspector.pk_attributes(mapper))
    for hook in hooks:
        statement, _ = hook.load_columns(select(), alias, "add")
        reads.extend(statement.selected_columns)
    return reads


def _read_columns(
    projection: Projection, rows: RowSet, row_aliases: Sequence[AliasedClass[Any]]
) -> list[ColumnElement[Any]]:
    """Returns the columns of the rows' FROM clauses that ``projection`` reads, each once, row-alias entities first."""
    reads: list[Any] = []
    for node, alias in projection.entities.items():
        if any(alias is row_alias for row_alias in row_aliases):
            reads.extend(_entity_reads(alias, projection.loaded.get(node), projection.hooks.get(node, ())))
    for join in projection.joins.values():
        if join.onclause is not None:
            reads.append(join.onclause)
        if isinstance(join.target, FromClause):
            reads.append(join.target)
    reads.extend(projection.columns)
    reads.extend(projection.column_map.values())
    reads.extend(column for columns in projection.identity_columns.values() for column in columns)
    reads.extend(term for _, term in projection.order_by)
    reads.extend(projection.root_aggregations)
    row_from_clauses = _row_from_clauses(rows)
    exported: list[ColumnElement[Any]] = []
    for read in reads:
        for element in visitors.iterate(clause_element(read)):
            if (
                isinstance(element, ColumnClause)
                and element.table in row_from_clauses
                and not any(same_column(element, column) for column in exported)
            ):
                exported.append(element)
    return exported


def _entities_over(
    selectable: FromClause,
    aliases: Sequence[AliasedClass[Any]],
    entities: Mapping[AliasedClass[Any], AliasedClass[Any]] | None = None,
) -> dict[AliasedClass[Any], AliasedClass[Any]]:
    """Builds, for each alias without one in ``entities``, the entity reading its columns from ``selectable``.

    An alias whose table another alias shares is aliased itself: ``aliased(mapper, selectable)`` matches columns by
    table column and would read the first alias's.
    """
    tables = Counter(inspect(alias).mapper.local_table for alias in aliases)
    over = dict(entities or {})
    for alias in aliases:
        mapper = inspect(alias).mapper
        shared = tables[mapper.local_table] > 1
        if alias not in over or shared:
            over[alias] = aliased(alias, selectable) if shared else aliased(mapper, selectable)
    return over


def materialize(level: Level, rows: RowSet, projection: Projection) -> QueryPlan:
    """Inlines ``rows`` next to ``projection`` when they only filter, else renders them as one FROM.

    A root level reads a page subquery, a relation the LATERAL or CTE of ``attach_rows``. Either exports the
    columns the projection reads from the rows' FROM clauses, and the projection is moved onto them, not joined again.
    """
    plan = _materialize(level, rows, projection)
    return share_ctes(plan) if level.kind == "root" else plan


def materialize_shared(
    parent: Level, rows: RowSet, projection: Projection, windows: Sequence[RankWindow]
) -> tuple[Join, Projection]:
    """Joins ``rows``, read once for the nodes of ``windows``, to ``parent``, and moves what they read onto it.

    Returns:
        The join, and ``projection`` with the page of each node.
    """
    row_aliases = _row_aliases(rows)
    exported = _read_columns(projection, rows, row_aliases)
    relation = windows[0].node.value.model_field
    db_features = parent.context.db_features
    join, pages = attach_shared_rows(rows, windows, exported, relation, parent.alias, db_features, is_outer=True)
    join, projection = _rebased(join, rows, projection, row_aliases)
    return join, replace(projection, pages={**projection.pages, **pages})
