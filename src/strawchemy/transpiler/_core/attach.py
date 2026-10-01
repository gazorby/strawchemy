"""The one join strategy: a child level or an aggregate becomes a LATERAL join, or a CTE join without LATERAL."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, func, inspect, null, select, true
from sqlalchemy.orm import RelationshipProperty, aliased
from sqlalchemy.orm import join as orm_join
from sqlalchemy.sql.functions import count as sqla_count

from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.exceptions import TranspilingError
from strawchemy.transpiler._core.render import (
    adapt_clauses,
    clause_element,
    render_rows,
    require_corresponding_column,
    same_column,
)
from strawchemy.transpiler._core.rowset import AggregateJoin, Join

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Literal

    from sqlalchemy import Label, Select, SQLColumnExpression
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression
    from sqlalchemy.sql.selectable import Join as SQLJoin

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._core.rowset import RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("attach_grouped", "attach_rows", "correlate_relation")


def _relationship(relation: QueryableAttribute[Any]) -> RelationshipProperty[Any]:
    relationship = relation.property
    assert isinstance(relationship, RelationshipProperty)
    return relationship


def _key_attributes(
    relationship: RelationshipProperty[Any], side: Literal["parent", "target"], alias: AliasedClass[Any]
) -> list[QueryableAttribute[Any]]:
    """Returns the local (``"parent"``) or remote (``"target"``) foreign keys of ``relationship``, read from ``alias``."""
    alias_insp = inspect(alias)
    columns = relationship.local_columns if side == "parent" else relationship.remote_side
    attrs = alias_insp.mapper.attrs
    keys = [column.key for column in columns if column.key is not None]
    if len(keys) != len(columns) or any(key not in attrs for key in keys):
        msg = (
            f"{relationship} goes through a secondary table and has its own ordering or pagination: "
            "this is unsupported on databases without LATERAL"
        )
        raise TranspilingError(msg)
    return [attrs[key].class_attribute.adapt_to_entity(alias_insp) for key in keys]


def _selected(statement: Select[Any], column: ColumnElement[Any] | QueryableAttribute[Any]) -> ColumnElement[Any]:
    """Returns the column ``statement`` selects for ``column``, which DISTINCT ON emulation may have wrapped."""
    clause = clause_element(column)
    for selected in statement.selected_columns:
        if selected is clause or clause in selected.proxy_set or same_column(selected, clause):
            return selected
    msg = f"column {column!r} is not selected by {statement!r}"  # pragma: no cover  # defensive
    raise TranspilingError(msg)  # pragma: no cover  # defensive


def _lateral_rows(  # noqa: PLR0917
    rows: RowSet,
    node: QueryNodeType,
    columns: Sequence[ColumnElement[Any]],
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    db_features: DatabaseFeatures,
    *,
    is_outer: bool,
) -> tuple[Join, tuple[UnaryExpression[Any], ...]]:
    target = rows.source
    target_insp = inspect(target)
    aliased_relation = getattr(parent_alias, relation.key).of_type(target_insp)

    def correlate(statement: Select[Any]) -> Select[Any]:
        correlated = correlate_relation(statement, aliased_relation, target)
        # Emulated DISTINCT ON wraps the statement in a subquery, which must not keep the outer row as a FROM.
        return correlated.correlate_except() if rows.distinct_on else correlated

    rendered = render_rows(dataclasses.replace(rows, edits=(*rows.edits, correlate)), columns, db_features)
    lateral = rendered.statement.lateral()
    lateral_alias = aliased(target_insp.mapper, lateral, flat=True)
    join = Join(("relation", node), lateral, true(), is_outer, lateral_alias)
    return join, adapt_clauses(rendered.order_by, lateral)


def _cte_rows(  # noqa: PLR0917
    rows: RowSet,
    node: QueryNodeType,
    columns: Sequence[ColumnElement[Any]],
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    db_features: DatabaseFeatures,
    *,
    is_outer: bool,
) -> tuple[Join, tuple[UnaryExpression[Any], ...]]:
    """Builds a CTE running ``rows`` over all parents at once.

    The CTE ranks rows per parent; the join condition applies the limit and offset on that rank.
    """
    target = rows.source
    target_insp = inspect(target)
    remote_fks = _key_attributes(_relationship(relation), "target", target)
    primary_keys = [pk.adapt_to_entity(target_insp) for pk in SQLAlchemyInspector.pk_attributes(target_insp.mapper)]
    selection = list(columns)
    for extra in (*remote_fks, *primary_keys):
        if not any(same_column(clause_element(column), clause_element(extra)) for column in selection):
            selection.append(clause_element(extra))
    not_null = and_(*[fk.is_not(null()) for fk in remote_fks])
    unpaged = dataclasses.replace(
        rows, limit=None, offset=None, edits=(*rows.edits, lambda statement: statement.where(not_null))
    )
    rendered = render_rows(unpaged, selection, db_features, partition_by=[clause_element(fk) for fk in remote_fks])
    statement = rendered.statement.group_by(*rendered.statement.selected_columns)
    rank_column = _rank_column(
        [_selected(statement, fk) for fk in remote_fks],
        rendered.order_by,
        [_selected(statement, pk) for pk in primary_keys],
        rows,
    )
    if rank_column is not None:
        statement = statement.add_columns(rank_column)
    cte = statement.cte()
    cte_alias = aliased(target, cte)
    # Read after creating the CTE alias, so that the ON clause targets the CTE rather than a new alias.
    onclause: ColumnElement[bool] = getattr(parent_alias, relation.key).of_type(cte_alias)
    if rank_column is not None:
        onclause = and_(onclause, *_limit_offset_condition(require_corresponding_column(cte, rank_column), rows))
    join = Join(("relation", node), cte_alias, onclause, is_outer, cte_alias)
    return join, adapt_clauses(rendered.order_by, cte)


def _rank_column(
    remote_fks: Sequence[SQLColumnExpression[Any]],
    order_by: Sequence[SQLColumnExpression[Any]],
    primary_keys: Sequence[SQLColumnExpression[Any]],
    rows: RowSet,
) -> Label[int] | None:
    """Builds the ``dense_rank()`` column, per parent, that limit and offset are applied on.

    ``primary_keys`` break ties on ``order_by``, so that limit and offset count each row, as with LATERAL.

    Returns ``None`` when there is no ``order_by``, limit or offset.
    """
    if not (order_by or rows.limit is not None or rows.offset is not None):
        return None
    return func.dense_rank().over(partition_by=remote_fks, order_by=[*order_by, *primary_keys]).label(name="rank")


def _limit_offset_condition(rank_column: ColumnElement[Any], rows: RowSet) -> list[ColumnElement[bool]]:
    """Builds the predicates on ``rank_column`` that apply the limit and offset of ``rows``."""
    condition: list[ColumnElement[bool]] = []
    if rows.offset is not None:
        condition.append(rank_column > rows.offset)
    if rows.limit is not None:
        condition.append(rank_column <= (rows.offset + rows.limit if rows.offset else rows.limit))
    return condition


def _grouped_cte(
    labels: Sequence[Label[Any]],
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    function_alias: AliasedClass[Any],
) -> tuple[Any, Any, ColumnElement[bool]]:
    """Builds the CTE of ``labels`` grouped by the foreign keys to the parent, what to join and its ON clause."""
    relationship = _relationship(relation)
    statement = select(*labels)
    if relationship.secondary is not None:
        return _secondary_grouped_cte(statement, relation, parent_alias, function_alias)
    remote_fks = _key_attributes(relationship, "target", function_alias)
    cte = (
        statement.add_columns(*remote_fks)
        .group_by(*remote_fks)
        .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
        .cte()
    )
    cte_alias = aliased(function_alias, cte)
    return cte, cte_alias, getattr(parent_alias, relation.key).of_type(cte_alias)


def _secondary_grouped_cte(
    statement: Select[Any],
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    function_alias: AliasedClass[Any],
) -> tuple[Any, Any, ColumnElement[bool]]:
    """Builds the CTE of the aggregates of a relationship that goes through a secondary table.

    The CTE joins from its own copy of the parent, so SQLAlchemy writes the full ``primaryjoin`` and
    ``secondaryjoin`` conditions, and groups by the parent keys to join back to the query.
    """
    relationship = _relationship(relation)
    cte_parent_alias = aliased(inspect(parent_alias).mapper, flat=True)
    cte_keys = _key_attributes(relationship, "parent", cte_parent_alias)
    cte = (
        statement.select_from(cte_parent_alias)
        .join(getattr(cte_parent_alias, relation.key).of_type(inspect(function_alias)))
        .add_columns(*cte_keys)
        .group_by(*cte_keys)
        .cte()
    )
    cte_alias = aliased(cte_parent_alias, cte)
    onclause = and_(
        *[
            parent_key == cte_key
            for parent_key, cte_key in zip(
                _key_attributes(relationship, "parent", parent_alias),
                _key_attributes(relationship, "parent", cte_alias),
                strict=True,
            )
        ]
    )
    return cte, cte, onclause


def correlate_relation(
    statement: Select[Any], relation: QueryableAttribute[Any], target: AliasedClass[Any]
) -> Select[Any]:
    """Restricts ``statement``, a future LATERAL subquery, to the rows related to the outer query's row.

    With a secondary table, the ``secondaryjoin`` becomes a JOIN rather than a WHERE predicate. In the WHERE clause
    the secondary table would sit in FROM unjoined to ``target``, which SQLAlchemy reports as a cartesian product.
    """
    relationship = relation.property
    if not isinstance(relationship, RelationshipProperty) or relationship.secondary is None:
        return statement.where(relation)
    relation_join = orm_join(relation.parent, target, relation)
    primary_join = cast("SQLJoin", relation_join.left)
    correlation = cast("ColumnElement[bool]", primary_join.onclause)
    # Joined onto ``target`` rather than the reverse, so that ``target`` stays the left side of later joins from it.
    return statement.select_from(target).join(primary_join.right, relation_join.onclause).where(correlation)


def attach_rows(  # noqa: PLR0917
    rows: RowSet,
    node: QueryNodeType,
    columns: Sequence[ColumnElement[Any]],
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    db_features: DatabaseFeatures,
    *,
    is_outer: bool,
) -> tuple[Join, tuple[UnaryExpression[Any], ...]]:
    """Joins the rows of a child level to ``parent_alias`` through ``relation``.

    Returns:
        The join, and the child's final ORDER BY adapted onto the join's target, for the parent to append.
    """
    if db_features.supports_lateral:
        return _lateral_rows(rows, node, columns, relation, parent_alias, db_features, is_outer=is_outer)
    return _cte_rows(rows, node, columns, relation, parent_alias, db_features, is_outer=is_outer)


def attach_grouped(  # noqa: PLR0917
    functions: Mapping[QueryNodeType, Label[Any]],
    node: QueryNodeType,
    relation: QueryableAttribute[Any],
    parent_alias: AliasedClass[Any],
    function_alias: AliasedClass[Any],
    db_features: DatabaseFeatures,
) -> AggregateJoin:
    """Joins the aggregate ``functions``, built against ``function_alias``, computed for each row of ``parent_alias``."""
    labels = list(functions.values())
    if db_features.supports_lateral:
        aliased_relation = getattr(parent_alias, relation.key).of_type(inspect(function_alias))
        statement = correlate_relation(select(*labels), aliased_relation, function_alias)
        # Explicit, so that inside an EXISTS body, whose FROM is not ``parent_alias``, it still correlates.
        target = join_target = statement.correlate(parent_alias).lateral()
        onclause: ColumnElement[bool] = true()
    else:
        target, join_target, onclause = _grouped_cte(labels, relation, parent_alias, function_alias)
    is_outer = not db_features.supports_lateral
    columns: dict[QueryNodeType, ColumnElement[Any]] = {}
    for function_node, label in functions.items():
        column = require_corresponding_column(target, label)
        is_count = isinstance(label.element, sqla_count)
        columns[function_node] = func.coalesce(column, 0) if is_outer and is_count else column
    return AggregateJoin(("aggregate", node), join_target, onclause, is_outer, None, columns, left=parent_alias)
