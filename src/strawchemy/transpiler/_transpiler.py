"""Transpiles a GraphQL query into a SQLAlchemy query.

This module contains the QueryTranspiler class, which is responsible for
converting a GraphQL query into a SQLAlchemy query.

Classes:
    QueryTranspiler: Transpiles a GraphQL query into a SQLAlchemy query.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy.orm import Mapper, RelationshipProperty, aliased
from typing_extensions import Self, override

from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO, OrderByDTO, OrderByRelationFilterDTO
from strawchemy.repository.typing import DeclarativeT, QueryExecutorT
from strawchemy.transpiler._executor import SyncQueryExecutor
from strawchemy.transpiler._planner import plan_query
from strawchemy.transpiler._query import HookApplier, Join, QueryGraph
from strawchemy.transpiler._scope import AliasContext
from strawchemy.transpiler._strategies import select_join_strategy

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy import Dialect, Select
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement

    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import OrderByExpr, QueryNodeType, SupportedDialect

__all__ = ("QueryTranspiler",)


class QueryTranspiler(Generic[DeclarativeT]):
    """Transpiles a GraphQL query into a SQLAlchemy query."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        statement: Select[tuple[DeclarativeT]] | None = None,
        scope: AliasContext[DeclarativeT] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> None:
        """Initializes the QueryTranspiler.

        Args:
            model: The SQLAlchemy model to transpile queries for.
            dialect: The SQLAlchemy dialect to use.
            statement: An optional base SQLAlchemy statement to build upon.
            scope: An optional existing AliasContext.
            query_hooks: Optional hooks to apply during query transpilation.
            deterministic_ordering: Whether to ensure deterministic ordering of results.
            default_order_by: Default ordering applied when the client supplies no order.
                Each expression must reference a mapped column of the root model; validated on first use.
        """
        supported_dialect = cast("SupportedDialect", dialect.name)

        self._inspector = SQLAlchemyGraphQLInspector(supported_dialect, [model.registry])
        self._join_strategy = select_join_strategy(self._inspector.db_features)
        self._statement = statement
        self._deterministic_ordering = deterministic_ordering
        self._default_order_by: list[OrderByExpr] = list(default_order_by or [])

        self.dialect = dialect
        self.context = scope or AliasContext(model, supported_dialect, inspector=self._inspector)

        self._hook_applier = HookApplier(self.context, query_hooks or defaultdict(list))

    @contextmanager
    def _sub_context(self, model: type[Any], root_alias: AliasedClass[Any]) -> Iterator[Self]:
        """Creates a new scope for a sub-query.

        Args:
            model: The SQLAlchemy model to create a scope for.
            root_alias: The aliased class to use as the root of the scope.

        Yields:
            A new transpiler instance with the sub-scope.
        """
        current_scope, sub_scope = self.context, self.context.sub(model, root_alias)
        try:
            self.context = sub_scope
            yield self
        finally:
            self.context = current_scope

    def _join(self, node: QueryNodeType, is_outer: bool = False) -> Join:
        """Creates a join object for a query node.

        Args:
            node: The query node to create a join for.
            is_outer: Whether to create an outer join.

        Returns:
            A join object containing the join information.
        """
        aliased_attribute = self.context.aliased_attribute(node)
        relation_filter = node.metadata.data.relation_filter

        if not relation_filter:
            return Join(aliased_attribute, node=node, is_outer=is_outer)

        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        target_mapper: Mapper[Any] = relationship.mapper.mapper
        target_alias: AliasedClass[Any] = cast("AliasedClass[Any]", aliased(target_mapper, flat=True))
        order_by = relation_filter.order_by if isinstance(relation_filter, OrderByRelationFilterDTO) else []

        with self._sub_context(target_mapper.class_, target_alias):
            query_graph = QueryGraph(self.context, order_by=order_by)  # ty:ignore[invalid-argument-type]
            plan = plan_query(
                query_graph,
                self.context,
                self._inspector.db_features,
                self.dialect,
                self._hook_applier,
                self._join,
                limit=relation_filter.limit,
                offset=relation_filter.offset,
                default_order_by=self._default_order_by,
                deterministic_ordering=self._deterministic_ordering,
                statement=None,
            )
        join = self._join_strategy.relation_join(self.context, node, target_alias, plan, is_outer)
        join.order_nodes = query_graph.order_by_nodes
        return join

    def select_executor(
        self,
        selection_tree: QueryNodeType | None = None,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        executor_cls: type[QueryExecutorT] = SyncQueryExecutor,  # ty: ignore[invalid-parameter-default]  # concrete default cannot satisfy an open TypeVar; overloading is not worth the verbosity
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        """Creates a QueryExecutor that executes a SQLAlchemy query based on a selection tree.

        This method builds a QueryExecutor that can execute a SQLAlchemy query with various
        options like filtering, ordering, pagination, and aggregations. The query is built
        from a selection tree that defines which fields to select and how they relate to
        each other.

        Args:
            selection_tree: Tree structure defining fields to select and their relationships.
                If None, only ID fields are selected.
            dto_filter: Filter conditions to apply to the query.
            order_by: List of fields and directions to sort the results by.
            limit: Maximum number of results to return.
            offset: Number of results to skip before returning.
            distinct_on: Fields to apply DISTINCT ON to.
            allow_null: Whether to allow null values in filter conditions.
            executor_cls: Executor type to return. Defaults to SyncQueryExecutor.
            execution_options: Options for statement execution.

        Returns:
            A QueryExecutor instance that can execute the built query.

        Example:
            ```python
            # Create an executor that selects user data with filtering and ordering
            executor = transpiler.select_executor(
                selection_tree=user_fields_tree,
                dto_filter=BooleanFilterDTO(field="age", op="gt", value=18),
                order_by=[OrderByDTO(field="name", direction="ASC")],
                limit=10
            )
            results = await executor.execute() # If using an async executor
            ```
        """
        query_graph = QueryGraph(
            self.context,
            selection_tree=selection_tree,
            dto_filter=dto_filter,
            order_by=order_by or [],
            distinct_on=distinct_on or [],
        )
        plan = plan_query(
            query_graph,
            ctx=self.context,
            db_features=self._inspector.db_features,
            dialect=self.dialect,
            hook_applier=self._hook_applier,
            join_builder=self._join,
            limit=limit,
            offset=offset,
            allow_null=allow_null,
            default_order_by=self._default_order_by,
            deterministic_ordering=self._deterministic_ordering,
            statement=self._statement,
        )
        return executor_cls(
            plan=plan,
            id_field_definitions=self.context.id_field_definitions(self.context.model),
            execution_options=execution_options,
        )

    def filter_expressions(self, dto_filter: BooleanFilterDTO) -> list[ColumnElement[bool]]:
        query_graph = QueryGraph(self.context, dto_filter=dto_filter)
        plan = plan_query(
            query_graph,
            ctx=self.context,
            db_features=self._inspector.db_features,
            dialect=self.dialect,
            hook_applier=self._hook_applier,
            join_builder=self._join,
            default_order_by=self._default_order_by,
            deterministic_ordering=self._deterministic_ordering,
            statement=self._statement,
        )
        return list(plan.where)

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.context.model}>"
