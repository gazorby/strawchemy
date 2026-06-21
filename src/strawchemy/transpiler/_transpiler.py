"""Transpiles a GraphQL query into a SQLAlchemy query.

This module contains the Transpiler class, a thin facade over a
``PlanContext`` that builds executors and filter expressions via ``plan_query``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import override

from strawchemy.repository.typing import DeclarativeT, QueryExecutorT
from strawchemy.transpiler._executor import SyncQueryExecutor
from strawchemy.transpiler._planner import PlanContext, plan_query
from strawchemy.transpiler._query import QueryGraph

if TYPE_CHECKING:
    from collections import defaultdict
    from collections.abc import Sequence

    from sqlalchemy import Dialect, Select
    from sqlalchemy.sql import ColumnElement

    from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import OrderByExpr, QueryNodeType

__all__ = ("Transpiler",)


class Transpiler(Generic[DeclarativeT]):
    """Transpiles a GraphQL query into a SQLAlchemy query."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        statement: Select[tuple[DeclarativeT]] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> None:
        """Initializes the Transpiler.

        Args:
            model: The SQLAlchemy model to transpile queries for.
            dialect: The SQLAlchemy dialect to use.
            statement: An optional base SQLAlchemy statement to build upon.
            query_hooks: Optional hooks to apply during query transpilation.
            deterministic_ordering: Whether to ensure deterministic ordering of results.
            default_order_by: Default ordering applied when the client supplies no order.
        """
        self.context: PlanContext[DeclarativeT] = PlanContext.create(
            model,
            dialect,
            statement=statement,
            query_hooks=query_hooks,
            deterministic_ordering=deterministic_ordering,
            default_order_by=default_order_by,
        )

    def select_executor(
        self,
        selection_tree: QueryNodeType | None = None,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        executor_cls: type[QueryExecutorT] = SyncQueryExecutor,  # ty: ignore[invalid-parameter-default]
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        """Creates a QueryExecutor for a selection tree.

        Args:
            selection_tree: Tree of fields to select and their relationships.
            dto_filter: Filter conditions to apply.
            order_by: Fields and directions to sort by.
            limit: Maximum number of results.
            offset: Number of results to skip.
            distinct_on: Fields to apply DISTINCT ON to.
            allow_null: Whether to allow null values in filter conditions.
            executor_cls: Executor type to return. Defaults to SyncQueryExecutor.
            execution_options: Options for statement execution.

        Returns:
            A QueryExecutor instance that can execute the built query.
        """
        query_graph = QueryGraph(
            self.context.aliases,
            selection_tree=selection_tree,
            dto_filter=dto_filter,
            order_by=order_by or [],
            distinct_on=distinct_on or [],
        )
        plan = plan_query(query_graph, self.context, limit=limit, offset=offset, allow_null=allow_null)
        return executor_cls(
            plan=plan,
            id_field_definitions=self.context.aliases.id_field_definitions(self.context.aliases.model),
            execution_options=execution_options,
        )

    def filter_expressions(self, dto_filter: BooleanFilterDTO) -> list[ColumnElement[bool]]:
        """Builds the WHERE expressions for a filter DTO.

        Args:
            dto_filter: The filter conditions to convert.

        Returns:
            The list of boolean WHERE expressions.
        """
        query_graph = QueryGraph(self.context.aliases, dto_filter=dto_filter)
        plan = plan_query(query_graph, self.context)
        return list(plan.where)

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.context.aliases.model}>"
