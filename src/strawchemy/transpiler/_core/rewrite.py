"""The base of the rewriters that move a projection from some FROM clauses onto others."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeVar, cast

from sqlalchemy.orm import QueryableAttribute
from sqlalchemy.sql import visitors

from strawchemy.transpiler._core.rowset import AggregateJoin

if TYPE_CHECKING:
    from sqlalchemy import ClauseElement
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, FromClause
    from sqlalchemy.sql.visitors import ExternallyTraversible

    from strawchemy.transpiler._core.rowset import Join, Projection

__all__ = ("PlanRewriter",)


_Clause = TypeVar("_Clause", bound="ClauseElement")


class PlanRewriter(ABC):
    """Rewrites a projection through ``_replace``, ``_entity`` and ``_target``, which subclasses override.

    Each expression is rewritten once, so that one the projection holds twice, in ``columns`` and ``column_map``, stays
    one object: the executor reads rows by column object.
    """

    def __init__(self) -> None:
        self._rewritten: dict[int, Any] = {}

    @abstractmethod
    def _replace(self, element: ExternallyTraversible, **_: object) -> ExternallyTraversible | None:
        """Returns what replaces ``element`` in an expression, or ``None`` to keep it and visit its children."""

    @abstractmethod
    def _entity(self, alias: AliasedClass[Any]) -> AliasedClass[Any]: ...

    @abstractmethod
    def _target(self, target: FromClause | AliasedClass[Any]) -> FromClause | AliasedClass[Any]: ...

    def _expression(self, expression: _Clause) -> _Clause:
        key = id(expression)
        if key not in self._rewritten:
            self._rewritten[key] = visitors.replacement_traverse(
                cast("ExternallyTraversible", expression), {}, self._replace
            )
        return self._rewritten[key]

    def _join(self, join: Join) -> Join:
        target = self._target(join.target)
        criteria = tuple(map(self._expression, join.criteria))
        rewritten = replace(
            join,
            target=target,
            alias=None if join.alias is None else self._entity(join.alias),
            left=None if join.left is None else self._entity(join.left),
            onclause=self._onclause(join, target, criteria),
            criteria=criteria,
        )
        if isinstance(rewritten, AggregateJoin):
            columns = {node: self._expression(column) for node, column in rewritten.columns.items()}
            rewritten = replace(rewritten, columns=columns)
        return rewritten

    def _onclause(
        self, join: Join, target: FromClause | AliasedClass[Any], criteria: tuple[ColumnElement[bool], ...]
    ) -> ColumnElement[bool] | None:
        """Rewrites the ON clause of ``join``; a relationship ON clause is rebuilt from the entities replacing its ends."""
        onclause = join.onclause
        if not isinstance(onclause, QueryableAttribute):
            return None if onclause is None else self._expression(onclause)
        original = onclause.parent.entity
        parent = self._entity(original)
        if parent is original and target is join.target:
            return onclause
        relation = getattr(parent, onclause.key).of_type(target)
        return relation.and_(*criteria) if criteria else relation

    def projection(self, projection: Projection) -> Projection:
        # Joins are rewritten outer first, so that a join's target is rewritten before the joins reading it.
        by_depth = sorted(projection.joins.items(), key=lambda item: item[0][1].level)
        joins = {key: self._join(join) for key, join in by_depth}
        return replace(
            projection,
            entities={node: self._entity(alias) for node, alias in projection.entities.items()},
            columns=tuple(map(self._expression, projection.columns)),
            joins={key: joins[key] for key in projection.joins},
            order_by=tuple((priority, self._expression(term)) for priority, term in projection.order_by),
            column_map={node: self._expression(column) for node, column in projection.column_map.items()},
            identity_columns={
                node: tuple(map(self._expression, columns)) for node, columns in projection.identity_columns.items()
            },
            root_aggregations=tuple(map(self._expression, projection.root_aggregations)),
            pages={node: replace(page, rank=self._expression(page.rank)) for node, page in projection.pages.items()},
        )
