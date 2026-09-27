"""Builds the join of a relation that has its own plan, as a LATERAL subquery or, when unsupported, a CTE."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import and_, func, inspect, null, select, true
from sqlalchemy.orm import RelationshipProperty, aliased
from sqlalchemy.orm import join as orm_join
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.transpiler._plan import distinct_rows
from strawchemy.transpiler._query import Join

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Label, Select, SQLColumnExpression
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, FromClause
    from sqlalchemy.sql.elements import UnaryExpression
    from sqlalchemy.sql.selectable import Join as SQLJoin

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._aliasing import AliasContext
    from strawchemy.transpiler._plan import QueryPlan
    from strawchemy.typing import QueryNodeType

__all__ = ("CteJoinStrategy", "JoinStrategy", "LateralJoinStrategy", "correlate_relation", "select_join_strategy")


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
    return statement.select_from(primary_join.right).join(target, relation_join.onclause).where(correlation)


class JoinStrategy(Protocol):
    """Builds the join of a relation from the relation's own plan."""

    def relation_join(
        self,
        scope: AliasContext[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        plan: QueryPlan,
        *,
        selection: Sequence[SQLColumnExpression[Any]],
        is_outer: bool,
    ) -> Join:
        """Builds the join of the relation behind ``node``, running ``plan`` against ``target_alias``.

        ``selection`` holds the columns the subquery exposes to the outer query.
        """
        ...


class LateralJoinStrategy:
    """Builds relation joins using LATERAL subqueries."""

    def relation_join(
        self,
        scope: AliasContext[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        plan: QueryPlan,
        *,
        selection: Sequence[SQLColumnExpression[Any]],
        is_outer: bool,
    ) -> Join:
        """Builds a LATERAL join running ``plan`` for each row of the outer query."""
        target_insp = inspect(target_alias)
        aliased_attribute = scope.aliased_attribute(node)
        root_relation = aliased_attribute.of_type(target_insp)
        base_statement = select(target_insp).with_only_columns(*selection)
        if plan.emulates_distinct_on:
            unpaged_plan = dataclasses.replace(plan, limit=None, offset=None)
            statement, hook_order_by = unpaged_plan.apply_clauses(base_statement)
            statement = correlate_relation(statement, root_relation, target_alias)
            order_by = (*hook_order_by, *plan.order_by)
            statement, adapter = distinct_rows(statement.correlate_except(), plan.distinct_on, order_by)
            statement = (
                statement.order_by(*[adapter.traverse(expression) for expression in order_by])
                .limit(plan.limit)
                .offset(plan.offset)
            )
        else:
            statement, hook_order_by = plan.apply_clauses(base_statement)
            statement = correlate_relation(statement, root_relation, target_alias)
        statement = statement.lateral()
        lateral_alias = aliased(target_insp.mapper, statement, flat=True)
        scope.set_relation_alias(node, "target", lateral_alias)
        return Join(
            statement, node=node, is_outer=is_outer, onclause=true(), hook_order_by=_adapt(hook_order_by, statement)
        )


class CteJoinStrategy:
    """Builds relation joins as CTEs, for databases without LATERAL."""

    def relation_join(
        self,
        scope: AliasContext[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        plan: QueryPlan,
        *,
        selection: Sequence[SQLColumnExpression[Any]],
        is_outer: bool,
    ) -> Join:
        """Builds a CTE join running ``plan`` over all parents at once.

        The CTE ranks rows per parent; the join condition applies the limit and offset on that rank.
        """
        remote_fks = scope.inspect(node).foreign_key_columns("target", target_alias)
        primary_keys = scope.aliased_id_attributes(node, target_alias)
        unpaged_plan = dataclasses.replace(plan, limit=None, offset=None)
        base_statement = (
            select(*selection, *remote_fks)
            .group_by(*remote_fks, *selection)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
        )
        statement, hook_order_by = unpaged_plan.apply_clauses(base_statement)
        order_by = (*hook_order_by, *plan.order_by)
        if plan.emulates_distinct_on:
            statement, adapter = distinct_rows(statement, plan.distinct_on, order_by, remote_fks)
            rank_column = self._rank_column(
                [adapter.traverse(fk.__clause_element__()) for fk in remote_fks],
                [adapter.traverse(expression) for expression in order_by],
                [adapter.traverse(pk.__clause_element__()) for pk in primary_keys],
                plan,
            )
        else:
            rank_column = self._rank_column(remote_fks, order_by, primary_keys, plan)
        if rank_column is not None:
            statement = statement.add_columns(rank_column)
        statement = statement.cte()
        cte_alias = aliased(target_alias, statement)
        scope.set_relation_alias(node, "target", cte_alias)
        # Read after registering the CTE alias, so that the ON clause targets the CTE rather than a new alias.
        aliased_attribute = scope.aliased_attribute(node)
        limit_offset_condition: list[ColumnElement[bool]] = []
        if rank_column is not None:
            scoped_rank = scope.scoped_column(statement, rank_column.name)
            limit_offset_condition = self._limit_offset_condition(scoped_rank, plan)
        return Join(
            statement,
            node,
            onclause=and_(aliased_attribute, *limit_offset_condition),
            is_outer=is_outer,
            hook_order_by=_adapt(hook_order_by, statement),
        )

    @staticmethod
    def _rank_column(
        remote_fks: Sequence[SQLColumnExpression[Any]],
        order_by: Sequence[SQLColumnExpression[Any]],
        primary_keys: Sequence[SQLColumnExpression[Any]],
        plan: QueryPlan,
    ) -> Label[int] | None:
        """Builds the ``dense_rank()`` column, per parent, that limit and offset are applied on.

        ``primary_keys`` break ties on ``order_by``, so that limit and offset count each row, as with LATERAL.

        Returns ``None`` when there is no ``order_by``, limit or offset.
        """
        if not (order_by or plan.limit is not None or plan.offset is not None):
            return None
        return func.dense_rank().over(partition_by=remote_fks, order_by=[*order_by, *primary_keys]).label(name="rank")

    @staticmethod
    def _limit_offset_condition(rank_column: ColumnElement[Any], plan: QueryPlan) -> list[ColumnElement[bool]]:
        """Builds the predicates on ``rank_column`` that apply the plan's limit and offset."""
        condition: list[ColumnElement[bool]] = []
        if plan.offset is not None:
            condition.append(rank_column > plan.offset)
        if plan.limit is not None:
            condition.append(rank_column <= (plan.offset + plan.limit if plan.offset else plan.limit))
        return condition


def _adapt(clauses: Sequence[UnaryExpression[Any]], selectable: FromClause) -> tuple[UnaryExpression[Any], ...]:
    adapter = ClauseAdapter(selectable)
    return tuple(adapter.traverse(clause) for clause in clauses)


def select_join_strategy(db_features: DatabaseFeatures) -> JoinStrategy:
    """Returns the LATERAL strategy if the database supports it, the CTE strategy otherwise."""
    if db_features.supports_lateral:
        return LateralJoinStrategy()
    return CteJoinStrategy()
