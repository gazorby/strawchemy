"""Join strategies for relation joins.

This module defines the strategies used to build relation joins, selecting
between LATERAL joins and CTE-based joins depending on database capabilities.

Classes:
    JoinStrategy: Structural type for relation join strategies.
    LateralJoinStrategy: Builds relation joins using LATERAL subqueries.
    CteJoinStrategy: Builds relation joins using Common Table Expressions.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import and_, func, inspect, null, select, true
from sqlalchemy.orm import aliased

from strawchemy.transpiler._query import Join

if TYPE_CHECKING:
    from sqlalchemy import Label
    from sqlalchemy.orm import QueryableAttribute
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._query import Query
    from strawchemy.transpiler._scope import QueryScope
    from strawchemy.typing import QueryNodeType

__all__ = ("CteJoinStrategy", "JoinStrategy", "LateralJoinStrategy", "select_join_strategy")


class JoinStrategy(Protocol):
    """Structural type for relation-join construction (lateral or CTE)."""

    def relation_join(
        self,
        scope: QueryScope[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        query: Query,
        is_outer: bool,
    ) -> Join:
        """Builds the subquery join for a related collection.

        Args:
            scope: The query scope used to resolve aliases and inspections.
            node: The query node representing the relation to join.
            target_alias: The aliased class for the target of the join.
            query: The subquery definition for the join.
            is_outer: Whether to perform an outer join.

        Returns:
            A Join object representing the relation join.
        """
        ...


class LateralJoinStrategy:
    """Builds relation joins using LATERAL subqueries."""

    def relation_join(
        self,
        scope: QueryScope[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        query: Query,
        is_outer: bool,
    ) -> Join:
        """Creates a LATERAL join for a given node.

        Args:
            scope: The query scope used to resolve aliases and inspections.
            node: The query node representing the relation to join.
            target_alias: The aliased class for the target of the join.
            query: The subquery definition for the lateral join.
            is_outer: Whether to perform an outer join.

        Returns:
            A Join object representing the lateral join.
        """
        target_insp = inspect(target_alias)
        aliased_attribute = scope.aliased_attribute(node)
        node_inspect = scope.inspect(node)
        name = scope.key(node)
        root_relation = aliased_attribute.of_type(target_insp)
        base_statement = select(target_insp).with_only_columns(*node_inspect.selection(target_alias))
        statement = query.statement(base_statement).where(root_relation).lateral(name)
        lateral_alias = aliased(target_insp.mapper, statement, name=name, flat=True)
        scope.set_relation_alias(node, "target", lateral_alias)
        return Join(statement, node=node, is_outer=is_outer, onclause=true())


class CteJoinStrategy:
    """Builds relation joins using Common Table Expressions.

    This is used when LATERAL joins are not supported by the database.
    """

    def relation_join(
        self,
        scope: QueryScope[Any],
        node: QueryNodeType,
        target_alias: AliasedClass[Any],
        query: Query,
        is_outer: bool,
    ) -> Join:
        """Creates a CTE-based join for a given node.

        This is used when LATERAL joins are not supported by the database.

        Args:
            scope: The query scope used to resolve aliases and inspections.
            node: The query node representing the relation to join.
            target_alias: The aliased class for the target of the join.
            query: The subquery definition for the CTE.
            is_outer: Whether to perform an outer join.

        Returns:
            A Join object representing the CTE-based join.
        """
        aliased_attribute = scope.aliased_attribute(node)
        remote_fks = scope.inspect(node).foreign_key_columns("target", target_alias)
        rank_column = self._rank_column(remote_fks, query)
        name = scope.key(node)
        # Remove limit/offset in CTE as it's applied in the WHERE clause of the main query
        query_wihtout_limit_offset = dataclasses.replace(query, offset=None, limit=None)
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
        statement = query_wihtout_limit_offset.statement(base_statement).cte(name)
        cte_alias = aliased(target_alias, statement, name=name)
        scope.set_relation_alias(node, "target", cte_alias)
        limit_offset_condition: list[ColumnElement[bool]] = []
        if rank_column is not None:
            scoped_rank = scope.scoped_column(statement, rank_column.name)
            limit_offset_condition = self._limit_offset_condition(scoped_rank, query)
        return Join(statement, node, onclause=and_(aliased_attribute, *limit_offset_condition), is_outer=is_outer)

    @staticmethod
    def _rank_column(remote_fks: list[QueryableAttribute[Any]], query: Query) -> Label[int] | None:
        """Builds the ``dense_rank()`` column used to emulate limit/offset per partition.

        Args:
            remote_fks: The remote foreign key columns to partition the ranking by.
            query: The query providing the ordering and limit/offset settings.

        Returns:
            A labeled rank column, or None when neither ordering nor limit/offset apply.
        """
        if not (query.order_by or query.limit is not None or query.offset is not None):
            return None
        return (
            func.dense_rank()
            .over(partition_by=remote_fks, order_by=query.order_by.expressions if query.order_by else None)
            .label(name="rank")
        )

    @staticmethod
    def _limit_offset_condition(rank_column: Label[Any], query: Query) -> list[ColumnElement[bool]]:
        """Builds the rank-based predicates emulating the query's limit/offset.

        Args:
            rank_column: The scoped rank column resolved against the built CTE.
            query: The query providing the limit and offset settings.

        Returns:
            The list of boolean predicates restricting rows to the requested window.
        """
        condition: list[ColumnElement[bool]] = []
        if query.offset is not None:
            condition.append(rank_column > query.offset)
        if query.limit is not None:
            condition.append(rank_column <= (query.offset + query.limit if query.offset else query.limit))
        return condition


def select_join_strategy(db_features: DatabaseFeatures) -> JoinStrategy:
    """Selects the relation join strategy for the given database features.

    Args:
        db_features: The database features describing dialect capabilities.

    Returns:
        A LateralJoinStrategy if LATERAL joins are supported, a CteJoinStrategy otherwise.
    """
    if db_features.supports_lateral:
        return LateralJoinStrategy()
    return CteJoinStrategy()
