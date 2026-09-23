"""Entry point turning a GraphQL query into a SQLAlchemy statement and its executor."""

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
    """Plans the GraphQL queries of one model into SQLAlchemy statements."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        *,
        statement: Select[tuple[DeclarativeT]] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> None:
        """Creates a transpiler whose root rows are restricted by ``statement``, if given.

        ``default_order_by`` applies when the client asks for no ordering; ``deterministic_ordering`` then adds the
        primary keys so that row order is stable.
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
        *,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        executor_cls: type[QueryExecutorT] = SyncQueryExecutor,  # ty: ignore[invalid-parameter-default]
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        """Plans the query into one statement and returns an ``executor_cls`` running it."""
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
        """Returns the WHERE predicates of ``dto_filter`` on the root model."""
        query_graph = QueryGraph(self.context.aliases, dto_filter=dto_filter)
        plan = plan_query(query_graph, self.context)
        return list(plan.where)

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.context.aliases.model}>"
