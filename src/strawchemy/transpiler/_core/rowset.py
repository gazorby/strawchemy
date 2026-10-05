"""Frozen data describing which rows a level selects (``RowSet``) and what it reads from them (``Projection``)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from sqlalchemy import Select, select
from typing_extensions import Self

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy import Label
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, FromClause
    from sqlalchemy.sql.elements import UnaryExpression

    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import QueryNodeType

__all__ = (
    "AggregateJoin",
    "AliasPage",
    "Join",
    "JoinKey",
    "JoinKind",
    "OrderPriority",
    "Projection",
    "RowSet",
    "StatementEdit",
    "is_where_only",
)


_Joins: TypeAlias = "Mapping[JoinKey, Join]"
_OrderBy: TypeAlias = "tuple[tuple[OrderPriority, UnaryExpression[Any]], ...]"

JoinKind: TypeAlias = Literal["relation", "aggregate"]
JoinKey: TypeAlias = "tuple[JoinKind, QueryNodeType]"
StatementEdit: TypeAlias = "Callable[[Select[Any]], Select[Any]]"


class OrderPriority(IntEnum):
    HOOK = 0
    CLIENT = 1
    DETERMINISTIC = 2


@dataclass(frozen=True)
class Join:
    """A relation join; ``alias`` is the entity alias the joined rows are read from. Joins render in node-depth order."""

    key: JoinKey
    target: FromClause | AliasedClass[Any]
    onclause: ColumnElement[bool] | None
    is_outer: bool
    alias: AliasedClass[Any] | None
    criteria: tuple[ColumnElement[bool], ...] = field(default=(), kw_only=True)
    """Predicates a relationship ON clause adds to the relationship's own condition."""
    left: AliasedClass[Any] | None = field(default=None, kw_only=True)
    """The FROM the join starts from, which its ON clause may not name, such as the row a LATERAL aggregates for."""


@dataclass(frozen=True)
class AggregateJoin(Join):
    """A join to the grouped aggregates of a node; ``columns`` maps each function node to its column on ``target``."""

    columns: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class AliasPage:
    """The objects a relation node keeps of the rows of an entity it may share, by the ``rank`` of each object."""

    rank: ColumnElement[int]
    offset: int | None
    limit: int | None

    def contains(self, rank: int) -> bool:
        offset = self.offset or 0
        return offset < rank and (self.limit is None or rank <= offset + self.limit)


@dataclass(frozen=True)
class RowSet:
    source: AliasedClass[Any]
    joins: _Joins = field(default_factory=dict)
    where: tuple[ColumnElement[bool], ...] = ()
    order_by: _OrderBy = ()
    distinct_on: tuple[ColumnElement[Any], ...] = ()
    limit: int | None = None
    offset: int | None = None
    edits: tuple[StatementEdit, ...] = ()

    def _edited(self) -> Select[Any]:
        statement = select(self.source)
        for edit in self.edits:
            statement = edit(statement)
        return statement

    @classmethod
    def over(cls, alias: AliasedClass[Any]) -> Self:
        return cls(source=alias)

    def join(self, key: JoinKey) -> Join | None:
        return self.joins.get(key)

    def with_join(self, join: Join) -> RowSet:
        """Adds ``join`` unless its key is taken, in which case the existing join stays."""
        joins = _with_join(self.joins, join)
        return self if joins is self.joins else replace(self, joins=joins)

    def with_where(self, *predicates: ColumnElement[bool]) -> RowSet:
        return replace(self, where=(*self.where, *predicates))

    def with_order_by(self, priority: OrderPriority, *expressions: UnaryExpression[Any]) -> RowSet:
        return replace(self, order_by=_with_order_by(self.order_by, priority, expressions))

    def with_edit(self, edit: StatementEdit) -> RowSet:
        return replace(self, edits=(*self.edits, edit))

    def only_filters(self, *, unordered: bool = False) -> bool:
        """Tells whether the rows can be filtered inline: no limit, offset or DISTINCT ON, edits add only WHERE.

        Args:
            unordered: Ignores the ORDER BY the edits add.
        """
        if self.limit is not None or self.offset is not None or self.distinct_on:
            return False
        edited = self._edited()
        return is_where_only(edited.order_by(None) if unordered else edited, select(self.source))

    def edits_shape_rows(self) -> bool:
        """Tells whether the edits add a LIMIT, OFFSET, DISTINCT, GROUP BY or HAVING, which change the rows read."""
        edited = self._edited()
        return bool(
            edited._limit_clause is not None  # noqa: SLF001
            or edited._offset_clause is not None  # noqa: SLF001
            or edited._distinct  # noqa: SLF001
            or edited._group_by_clauses  # noqa: SLF001
            or edited._having_criteria  # noqa: SLF001
        )

    def edits_where(self) -> ColumnElement[bool] | None:
        """Returns the WHERE the edits add to the rows' source."""
        return self._edited().whereclause


@dataclass(frozen=True)
class Projection:
    entities: Mapping[QueryNodeType, AliasedClass[Any]] = field(default_factory=dict)
    loaded: Mapping[QueryNodeType, tuple[str, ...]] = field(default_factory=dict)
    hooks: Mapping[QueryNodeType, tuple[QueryHook[Any], ...]] = field(default_factory=dict)
    columns: tuple[ColumnElement[Any], ...] = ()
    joins: _Joins = field(default_factory=dict)
    order_by: _OrderBy = ()
    """Terms of every level, outer level first; only the terms of one level are sorted by priority."""
    column_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    identity_columns: Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]] = field(default_factory=dict)
    root_aggregations: tuple[Label[Any], ...] = ()
    pages: Mapping[QueryNodeType, AliasPage] = field(default_factory=dict)

    @classmethod
    def over(cls, root_node: QueryNodeType, alias: AliasedClass[Any]) -> Self:
        return cls(entities={root_node: alias})

    def with_join(self, join: Join) -> Projection:
        joins = _with_join(self.joins, join)
        return self if joins is self.joins else replace(self, joins=joins)

    def with_loaded(self, node: QueryNodeType, *keys: str) -> Projection:
        return replace(self, loaded={**self.loaded, node: (*self.loaded.get(node, ()), *keys)})

    def with_hooks(self, node: QueryNodeType, *hooks: QueryHook[Any]) -> Projection:
        return replace(self, hooks={**self.hooks, node: (*self.hooks.get(node, ()), *hooks)})

    def with_columns(self, *columns: ColumnElement[Any]) -> Projection:
        return replace(self, columns=(*self.columns, *columns))

    def with_computed(self, node: QueryNodeType, column: ColumnElement[Any]) -> Projection:
        return replace(self, columns=(*self.columns, column), column_map={**self.column_map, node: column})

    def with_identity(self, node: QueryNodeType, columns: tuple[ColumnElement[Any], ...]) -> Projection:
        return replace(self, identity_columns={**self.identity_columns, node: columns})

    def with_root_aggregation(self, node: QueryNodeType, label: Label[Any]) -> Projection:
        return replace(
            self, column_map={**self.column_map, node: label}, root_aggregations=(*self.root_aggregations, label)
        )

    def with_order_by(self, priority: OrderPriority, *expressions: UnaryExpression[Any]) -> Projection:
        return replace(self, order_by=_with_order_by(self.order_by, priority, expressions))

    def with_page(self, node: QueryNodeType, page: AliasPage) -> Projection:
        return replace(self, pages={**self.pages, node: page})

    def merge(self, other: Projection) -> Projection:
        """Unions every mapping and tuple of ``other`` after those of ``self``."""
        joins = self.joins
        for join in other.joins.values():
            joins = _with_join(joins, join)
        loaded = {**self.loaded}
        for node, keys in other.loaded.items():
            loaded[node] = (*loaded.get(node, ()), *keys)
        hooks = {**self.hooks}
        for node, node_hooks in other.hooks.items():
            hooks[node] = (*hooks.get(node, ()), *node_hooks)
        return Projection(
            entities={**self.entities, **other.entities},
            loaded=loaded,
            hooks=hooks,
            columns=(*self.columns, *other.columns),
            joins=joins,
            order_by=(*self.order_by, *other.order_by),
            column_map={**self.column_map, **other.column_map},
            identity_columns={**self.identity_columns, **other.identity_columns},
            root_aggregations=(*self.root_aggregations, *other.root_aggregations),
            pages={**self.pages, **other.pages},
        )


def _with_join(joins: _Joins, join: Join) -> _Joins:
    return joins if join.key in joins else {**joins, join.key: join}


def _with_order_by(
    order_by: _OrderBy, priority: OrderPriority, expressions: tuple[UnaryExpression[Any], ...]
) -> _OrderBy:
    return (*order_by, *((priority, expression) for expression in expressions))


def is_where_only(statement: Select[Any], base: Select[Any]) -> bool:
    """Tells whether ``statement`` is ``base`` with WHERE clauses only."""
    where = statement.whereclause
    expected = base if where is None else base.where(where)
    try:
        return statement.compare(expected)
    except AttributeError:  # pragma: no cover  # defensive: uncomparable statement, not a WHERE-only edit
        return False
