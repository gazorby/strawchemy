"""One CTE for the joins of a plan whose CTEs have identical bodies, apart from their rank windows."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from sqlalchemy import func, inspect
from sqlalchemy.orm import aliased
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause, Label, Over
from sqlalchemy.sql.selectable import CTE, FromClause, Select
from sqlalchemy.sql.selectable import Join as SQLJoin

from strawchemy.transpiler._core.render import clause_element
from strawchemy.transpiler._core.rewrite import PlanRewriter

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import ClauseElement
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.visitors import ExternallyTraversible

    from strawchemy.transpiler._core.plan import QueryPlan
    from strawchemy.transpiler._core.rowset import Join, RowSet

__all__ = ("share_ctes",)

_Body: TypeAlias = "tuple[str, dict[str, Any]]"
_Targets: TypeAlias = "dict[CTE, tuple[CTE, dict[ColumnElement[Any], ColumnElement[Any]]]]"
"""What replaces each CTE of a group, and the column replacing each of its columns."""

_RANK_FUNCTIONS = frozenset({"dense_rank", "row_number"})
_RANK_NAME = re.compile(r"rank(?:_\d+)?")


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


@dataclass
class _Group:
    """CTEs read as one: each distinct body is a variant, differing from the other variants in its ranks only."""

    bodies: list[_Body] = field(default_factory=list)
    variants: list[CTE] = field(default_factory=list)
    members: list[tuple[CTE, int]] = field(default_factory=list)
    """Each CTE of the group, the first one first, and the index of its variant."""

    def add(self, cte: CTE, body: _Body) -> None:
        variant = next((index for index, variant_body in enumerate(self.bodies) if variant_body == body), None)
        if variant is None:
            self.bodies.append(body)
            self.variants.append(cte)
            variant = len(self.variants) - 1
        self.members.append((cte, variant))


def _ctes(joins: Iterable[Join]) -> list[CTE]:
    """Returns the CTEs ``joins`` read, each once, shallowest join first."""
    ctes: list[CTE] = []
    for join in sorted(joins, key=lambda join: join.key[1].level):
        selectable = inspect(join.target).selectable if isinstance(join.target, AliasedClass) else join.target
        if isinstance(selectable, CTE) and not any(selectable is cte for cte in ctes):
            ctes.append(selectable)
    return ctes


def _compiled(statement: ClauseElement) -> _Body:
    """Compiles ``statement`` on its own, so that anonymous names are numbered the same in equal statements.

    The default string compiler renders every construct, so planning reads no more of the dialect than its name.
    """
    compiled = statement.compile()
    return compiled.string, compiled.params


def _is_rank(column: ColumnElement[Any]) -> bool:
    return (
        isinstance(column, Label)
        and _RANK_NAME.fullmatch(str(column.name)) is not None
        and isinstance(column.element, Over)
        and getattr(column.element.element, "name", None) in _RANK_FUNCTIONS
    )


def _unranked(statement: Select[Any]) -> Select[Any] | None:
    """Returns ``statement`` without its ranks but with their partition, or ``None`` unless its ranks share one.

    Without LIMIT, OFFSET, FETCH or DISTINCT, the ORDER BY orders nothing and is left out too.
    """
    windows: list[Over[Any]] = [column.element for column in statement.selected_columns if _is_rank(column)]
    partition = windows[0].partition_by if windows else None
    if partition is None or any(
        window.partition_by is None or not partition.compare(window.partition_by) for window in windows
    ):
        return None
    unranked = statement.with_only_columns(
        *[column for column in statement.selected_columns if not _is_rank(column)], maintain_column_froms=True
    )
    first_rows = (unranked._limit_clause, unranked._offset_clause, unranked._fetch_clause)  # noqa: SLF001
    if all(clause is None for clause in first_rows) and not unranked._distinct:  # noqa: SLF001
        unranked = unranked.order_by(None)
    return unranked.add_columns(func.count().over(partition_by=partition).label("partition"))


def _groups(ctes: Iterable[CTE]) -> list[_Group]:
    """Groups ``ctes`` by body, comparing the bodies of rank CTEs without their rank columns."""
    groups: list[tuple[tuple[bool, _Body], _Group]] = []
    for cte in ctes:
        body = cte.element
        unranked = _unranked(body) if isinstance(body, Select) else None
        key = (False, _compiled(body)) if unranked is None else (True, _compiled(unranked))
        group = next((group for group_key, group in groups if group_key == key), None)
        if group is None:
            group = _Group()
            groups.append((key, group))
        group.add(cte, _compiled(body))
    return [group for _, group in groups]


def _leaf_froms(statement: Select[Any]) -> list[FromClause]:
    """Returns the FROM clauses of ``statement``, each join replaced by its sides, in rendering order."""
    leaves: list[FromClause] = []
    pending = list(statement.get_final_froms())
    while pending:
        from_clause = pending.pop(0)
        if isinstance(from_clause, SQLJoin):
            pending[:0] = [from_clause.left, from_clause.right]
        else:
            leaves.append(from_clause)
    return leaves


def _moved_window(window: Over[Any], mapping: Mapping[FromClause, FromClause]) -> Over[Any] | None:
    """Rewrites ``window`` onto the FROM clauses ``mapping`` maps its own to, or returns ``None`` if one is not mapped."""
    for element in visitors.iterate(window):
        if (
            isinstance(element, ColumnClause)
            and element.table is not None
            and (element.table not in mapping or mapping[element.table].c.get(element.key) is None)
        ):
            return None

    def moved(element: ExternallyTraversible, **_: object) -> ExternallyTraversible | None:
        if isinstance(element, ColumnClause) and element.table is not None:
            return mapping[element.table].c[element.key]
        return None

    return visitors.replacement_traverse(window, {}, moved)


def _merged(variants: Sequence[CTE]) -> tuple[CTE, list[list[int]]] | None:
    """Builds one CTE over the body of the first of ``variants``, with the rank columns of them all.

    The rank columns are named ``rank_1`` onward, in the order of ``variants``.

    Returns:
        The CTE and, per variant, the position in it of each column of the variant; ``None`` if the windows of some
        variant cannot be moved onto the first's body.
    """
    # Only rank CTEs, whose bodies are SELECTs, have more than one variant.
    statements = [cast("Select[Any]", variant.element) for variant in variants]
    kept = statements[0]
    kept_froms = _leaf_froms(kept)
    names = (f"rank_{number}" for number in itertools.count(1))
    selected: list[ColumnElement[Any]] = []
    unranked_positions: list[int] = []
    for column in kept.selected_columns:
        if not _is_rank(column):
            unranked_positions.append(len(selected))
        selected.append(column.element.label(next(names)) if _is_rank(column) else column)
    positions = [list(range(len(selected)))]
    for statement in statements[1:]:
        # The bodies compiled equal without their ranks but with every FROM clause, so these pair up in order.
        mapping = dict(zip(_leaf_froms(statement), kept_froms, strict=True))
        unranked = iter(unranked_positions)
        variant_positions: list[int] = []
        for column in statement.selected_columns:
            if not _is_rank(column):
                variant_positions.append(next(unranked))
                continue
            window = _moved_window(column.element, mapping)
            if window is None:
                return None
            variant_positions.append(len(selected))
            selected.append(window.label(next(names)))
        positions.append(variant_positions)
    return kept.with_only_columns(*selected, maintain_column_froms=True).cte(), positions


def _targets(group: _Group) -> _Targets | None:
    """Returns what replaces each CTE of ``group``: an alias of the first, or of their merged CTE for every one."""
    if len(group.variants) == 1:
        kept = group.variants[0]
        aliases = {cte: kept.alias() for cte, _ in group.members[1:]}
        return {cte: (alias, dict(zip(cte.c, alias.c, strict=True))) for cte, alias in aliases.items()}
    merged = _merged(group.variants)
    if merged is None:
        return None
    merged_cte, positions = merged
    targets: _Targets = {}
    for index, (cte, variant) in enumerate(group.members):
        target = merged_cte if index == 0 else merged_cte.alias()
        target_columns = list(target.c)
        replacing = zip(cte.c, positions[variant], strict=True)
        targets[cte] = (target, {column: target_columns[position] for column, position in replacing})
    return targets


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
    insp = inspect(entity)
    mapper = insp.mapper
    moved = aliased(mapper, alias)
    for prop in mapper.column_attrs:
        if insp.selectable.corresponding_column(prop.columns[0]) is None:
            continue
        column = clause_element(getattr(entity, prop.key))
        # Attributes read ORM-annotated copies, which hash as the column they copy.
        if column in columns and hash(clause_element(getattr(moved, prop.key))) != hash(columns[column]):
            return None
    return moved


def share_ctes(plan: QueryPlan) -> QueryPlan:
    """Joins one CTE, under an alias per join, where the joins of ``plan`` read CTEs with the same body.

    Bodies are compared compiled on their own, never by name, and rank CTEs without their ranks: the shared CTE then
    carries the ranks of them all. A group whose entities cannot be moved onto the shared CTE keeps its CTEs.
    Sharing returns a new plan rather than being part of rendering, so that the executor reads what the statement selects.
    """
    ctes = _ctes([*plan.rows.joins.values(), *plan.projection.joins.values()])
    if len(ctes) < 2:  # noqa: PLR2004
        return plan
    aliases: dict[CTE, CTE] = {}
    columns: dict[ColumnElement[Any], ColumnElement[Any]] = {}
    entities: dict[AliasedClass[Any], AliasedClass[Any]] = {}
    plan_entities = _entities_over(plan)
    for group in _groups(ctes):
        targets = _targets(group)
        if not targets:
            continue
        moved = {
            entity: _moved(entity, target, cte_columns)
            for cte, (target, cte_columns) in targets.items()
            for entity in plan_entities
            if inspect(entity).selectable is cte
        }
        if any(moved_entity is None for moved_entity in moved.values()):
            continue
        for cte, (target, cte_columns) in targets.items():
            aliases[cte] = target
            columns.update(cte_columns)
        entities.update({entity: moved_entity for entity, moved_entity in moved.items() if moved_entity is not None})
    if not aliases:
        return plan
    return _Share(aliases, columns, entities).plan(plan)
