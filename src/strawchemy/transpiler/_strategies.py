"""Builds the join of a relation that has its own plan, as a LATERAL subquery or, when unsupported, a CTE."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import and_, func, inspect, null, select, true
from sqlalchemy.orm import RelationshipProperty, aliased
from sqlalchemy.orm import join as orm_join

from strawchemy.transpiler._query import Join

if TYPE_CHECKING:
    from sqlalchemy import Label, Select
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
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
        is_outer: bool,
    ) -> Join:
        """Builds the join of the relation behind ``node``, running ``plan`` against ``target_alias``."""
        ...


class LateralJoinStrategy:
    """Builds relation joins using LATERAL subqueries."""

    def relation_join(
        self,
        scope: AliasContext[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        plan: QueryPlan,
        is_outer: bool,
    ) -> Join:
        """Builds a LATERAL join running ``plan`` for each row of the outer query."""
        target_insp = inspect(target_alias)
        aliased_attribute = scope.aliased_attribute(node)
        node_inspect = scope.inspect(node)
        root_relation = aliased_attribute.of_type(target_insp)
        base_statement = select(target_insp).with_only_columns(*node_inspect.selection(target_alias))
        statement = correlate_relation(plan.apply_clauses(base_statement), root_relation, target_alias).lateral()
        lateral_alias = aliased(target_insp.mapper, statement, flat=True)
        scope.set_relation_alias(node, "target", lateral_alias)
        return Join(statement, node=node, is_outer=is_outer, onclause=true())


class CteJoinStrategy:
    """Builds relation joins as CTEs, for databases without LATERAL."""

    def relation_join(
        self,
        scope: AliasContext[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        plan: QueryPlan,
        is_outer: bool,
    ) -> Join:
        """Builds a CTE join running ``plan`` over all parents at once.

        The CTE ranks rows per parent; the join condition applies the limit and offset on that rank.
        """
        remote_fks = scope.inspect(node).foreign_key_columns("target", target_alias)
        rank_column = self._rank_column(remote_fks, plan)
        plan_wihtout_limit_offset = dataclasses.replace(plan, limit=None, offset=None)
        node_inspect = scope.inspect(node)
        remote_fks = node_inspect.foreign_key_columns("target", target_alias)
        selection = node_inspect.selection(target_alias)
        base_statement = (
            select(*selection, *remote_fks)
            .group_by(*remote_fks, *selection)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
        )
        if rank_column is not None:
            base_statement = base_statement.add_columns(rank_column)
        statement = plan_wihtout_limit_offset.apply_clauses(base_statement).cte()
        cte_alias = aliased(target_alias, statement)
        scope.set_relation_alias(node, "target", cte_alias)
        # Read after registering the CTE alias, so that the ON clause targets the CTE rather than a new alias.
        aliased_attribute = scope.aliased_attribute(node)
        limit_offset_condition: list[ColumnElement[bool]] = []
        if rank_column is not None:
            scoped_rank = scope.scoped_column(statement, rank_column.name)
            limit_offset_condition = self._limit_offset_condition(scoped_rank, plan)
        return Join(statement, node, onclause=and_(aliased_attribute, *limit_offset_condition), is_outer=is_outer)

    @staticmethod
    def _rank_column(remote_fks: list[QueryableAttribute[Any]], plan: QueryPlan) -> Label[int] | None:
        """Builds the ``dense_rank()`` column, per parent, that limit and offset are applied on.

        Returns ``None`` when the plan has no ordering, limit or offset.
        """
        if not (plan.order_by or plan.limit is not None or plan.offset is not None):
            return None
        return func.dense_rank().over(partition_by=remote_fks, order_by=plan.order_by or None).label(name="rank")

    @staticmethod
    def _limit_offset_condition(rank_column: ColumnElement[Any], plan: QueryPlan) -> list[ColumnElement[bool]]:
        """Builds the predicates on ``rank_column`` that apply the plan's limit and offset."""
        condition: list[ColumnElement[bool]] = []
        if plan.offset is not None:
            condition.append(rank_column > plan.offset)
        if plan.limit is not None:
            condition.append(rank_column <= (plan.offset + plan.limit if plan.offset else plan.limit))
        return condition


def select_join_strategy(db_features: DatabaseFeatures) -> JoinStrategy:
    """Returns the LATERAL strategy if the database supports it, the CTE strategy otherwise."""
    if db_features.supports_lateral:
        return LateralJoinStrategy()
    return CteJoinStrategy()
