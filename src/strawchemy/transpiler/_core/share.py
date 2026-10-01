"""One CTE for the joins of a plan whose CTEs have identical bodies."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import inspect
from sqlalchemy.orm import aliased
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.selectable import CTE, FromClause

from strawchemy.transpiler._core.render import clause_element
from strawchemy.transpiler._core.rewrite import PlanRewriter

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.visitors import ExternallyTraversible

    from strawchemy.transpiler._core.plan import QueryPlan
    from strawchemy.transpiler._core.rowset import Join, RowSet

__all__ = ("share_ctes",)


class _Share(PlanRewriter):
    """Moves a plan from each dropped CTE onto the alias of the kept CTE replacing it."""

    def __init__(
        self,
        aliases: Mapping[CTE, CTE],
        columns: Mapping[ColumnElement[Any], ColumnElement[Any]],
        entities: Mapping[AliasedClass[Any], AliasedClass[Any]],
    ) -> None:
        super().__init__()
        self._aliases = aliases
        self._columns = columns
        self._entities = entities

    def _rows(self, rows: RowSet) -> RowSet:
        return replace(
            rows,
            source=self._entity(rows.source),
            joins={key: self._join(join) for key, join in rows.joins.items()},
            where=tuple(map(self._expression, rows.where)),
            order_by=tuple((priority, self._expression(term)) for priority, term in rows.order_by),
        )

    def _replace(self, element: ExternallyTraversible, **_: object) -> ExternallyTraversible | None:
        if isinstance(element, CTE) and element in self._aliases:
            return self._aliases[element]
        if isinstance(element, ColumnClause) and element.table in self._aliases:
            return self._columns[element]
        return None

    def _entity(self, alias: AliasedClass[Any]) -> AliasedClass[Any]:
        return self._entities.get(alias, alias)

    def _target(self, target: FromClause | AliasedClass[Any]) -> FromClause | AliasedClass[Any]:
        if isinstance(target, AliasedClass):
            return self._entity(target)
        return self._aliases.get(target, target) if isinstance(target, CTE) else target

    def plan(self, plan: QueryPlan) -> QueryPlan:
        return replace(plan, rows=self._rows(plan.rows), projection=self.projection(plan.projection))


def _ctes(joins: Iterable[Join]) -> list[CTE]:
    """Returns the CTEs ``joins`` read, each once, shallowest join first."""
    ctes: list[CTE] = []
    for join in sorted(joins, key=lambda join: join.key[1].level):
        selectable = inspect(join.target).selectable if isinstance(join.target, AliasedClass) else join.target
        if isinstance(selectable, CTE) and not any(selectable is cte for cte in ctes):
            ctes.append(selectable)
    return ctes


def _body(cte: CTE) -> tuple[str, dict[str, Any]]:
    """Compiles the body of ``cte`` on its own, so that anonymous names are numbered the same in equal bodies.

    The default string compiler renders every construct, so planning reads no more of the dialect than its name.
    """
    compiled = cte.element.compile()
    return compiled.string, compiled.params


def _entities_over(plan: QueryPlan) -> list[AliasedClass[Any]]:
    """Returns every entity of ``plan``: projected, read by a join, or joined."""
    joins = [*plan.rows.joins.values(), *plan.projection.joins.values()]
    candidates = [
        plan.rows.source,
        *plan.projection.entities.values(),
        *(join.alias for join in joins if join.alias is not None),
        *(join.target for join in joins if isinstance(join.target, AliasedClass)),
    ]
    entities: list[AliasedClass[Any]] = []
    for entity in candidates:
        if not any(entity is seen for seen in entities):
            entities.append(entity)
    return entities


def _moved(
    entity: AliasedClass[Any], alias: CTE, columns: Mapping[ColumnElement[Any], ColumnElement[Any]]
) -> AliasedClass[Any] | None:
    """Builds ``entity`` over ``alias``, or returns ``None`` if some column it reads would not move to its counterpart.

    ``aliased`` matches columns by the table columns they proxy, which is ambiguous when the body selects two aliases
    of one table.
    """
    mapper = inspect(entity).mapper
    moved = aliased(mapper, alias)
    for prop in mapper.column_attrs:
        column = clause_element(getattr(entity, prop.key))
        # Attributes read ORM-annotated copies, which hash as the column they copy.
        if column in columns and hash(clause_element(getattr(moved, prop.key))) != hash(columns[column]):
            return None
    return moved


def share_ctes(plan: QueryPlan) -> QueryPlan:
    """Joins one CTE, under an alias per join, where the joins of ``plan`` read CTEs with identical bodies.

    Bodies are compared compiled on their own, never by name. A body whose entities cannot be moved onto the kept CTE
    keeps its own CTE. Sharing returns a new plan rather than being part of rendering, so that the executor reads the
    entities and columns the statement selects.
    """
    ctes = _ctes([*plan.rows.joins.values(), *plan.projection.joins.values()])
    if len(ctes) < 2:  # noqa: PLR2004
        return plan
    kept: list[tuple[CTE, tuple[str, dict[str, Any]]]] = []
    aliases: dict[CTE, CTE] = {}
    columns: dict[ColumnElement[Any], ColumnElement[Any]] = {}
    entities: dict[AliasedClass[Any], AliasedClass[Any]] = {}
    plan_entities = _entities_over(plan)
    for cte in ctes:
        body = _body(cte)
        shared = next((kept_cte for kept_cte, kept_body in kept if kept_body == body), None)
        if shared is None:
            kept.append((cte, body))
            continue
        alias = shared.alias()
        cte_columns: dict[ColumnElement[Any], ColumnElement[Any]] = dict(zip(cte.c, alias.c, strict=True))
        over = [entity for entity in plan_entities if inspect(entity).selectable is cte]
        moved = {entity: _moved(entity, alias, cte_columns) for entity in over}
        if any(moved_entity is None for moved_entity in moved.values()):
            continue
        aliases[cte] = alias
        columns.update(cte_columns)
        entities.update({entity: moved_entity for entity, moved_entity in moved.items() if moved_entity is not None})
    if not aliases:
        return plan
    return _Share(aliases, columns, entities).plan(plan)
