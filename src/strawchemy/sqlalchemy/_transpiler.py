"""Transpiles a GraphQL query into a SQLAlchemy query.

This module contains the Transpiler class, which is responsible for
converting a GraphQL query into a SQLAlchemy query. It also defines
several helper classes and functions that are used in the transpilation
process.

Classes:
    Transpiler: Transpiles a GraphQL query into a SQLAlchemy query.

Data classes:
    _Join: Represents a join between two tables.
    _Query: Represents a SQLAlchemy query.
    _AggregationJoin: Represents a join for aggregations.
    _Conjunction: Represents a conjunction of boolean expressions.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generic, Self, override

from sqlalchemy import (
    Dialect,
    Label,
    Select,
    and_,
    inspect,
    not_,
    null,
    or_,
    select,
    true,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapper,
    QueryableAttribute,
    RelationshipProperty,
    aliased,
    class_mapper,
    contains_eager,
    load_only,
    raiseload,
)
from strawchemy.graphql.constants import AGGREGATIONS_KEY
from strawchemy.graphql.dto import (
    AggregationFilter,
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)
from strawchemy.graphql.filters import GraphQLComparison

from ._executor import SyncQueryExecutor
from ._query import (
    AggregationJoin,
    Conjunction,
    DistinctOn,
    Join,
    OrderBy,
    Query,
    QueryGraph,
    Where,
)
from ._scope import QueryScope
from .exceptions import TranspilingError
from .inspector import SQLAlchemyGraphQLInspector
from .typing import (
    DeclarativeT,
    QueryExecutorT,
    QueryHookCallableWithoutInfo,
    SQLAlchemyOrderByNode,
    SQLAlchemyQueryNode,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql.elements import NamedColumn

__all__ = ("Transpiler",)


class Transpiler(Generic[DeclarativeT]):
    """Transpiles a GraphQL query into a SQLAlchemy query."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        statement: Select[tuple[DeclarativeT]] | None = None,
        scope: QueryScope[DeclarativeT] | None = None,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHookCallableWithoutInfo[Any]]] | None = None,
    ) -> None:
        self._inspector = SQLAlchemyGraphQLInspector([model.registry])
        self._sub_query_root_alias = aliased(class_mapper(model), name=model.__tablename__, flat=True)
        self._aggregation_name_prefix: str = "aggregation"
        self._aggregation_joins: dict[SQLAlchemyQueryNode, AggregationJoin] = {}
        self._query_hooks = query_hooks or defaultdict(list)
        self._statement = statement

        self.dialect = dialect
        self.scope = scope or QueryScope(model, inspector=self._inspector)

    def _base_statement(self) -> Select[tuple[DeclarativeT]]:
        if self._statement is not None:
            root_mapper = class_mapper(self.scope.model)
            alias = self._statement.subquery().alias()
            aliased_cls = aliased(root_mapper, alias)
            on_clause = and_(
                *[
                    getattr(self.scope.root_alias, attr.key) == getattr(aliased_cls, attr.key)
                    for attr in self._inspector.pk_attributes(root_mapper)
                ]
            )
            return select(self.scope.root_alias).join(alias, onclause=on_clause)
        return select(self.scope.root_alias)

    @contextmanager
    def _sub_scope(self, model: type[Any], root_alias: AliasedClass[Any]) -> Iterator[Self]:
        """Creates a new scope for a sub-query.

        Args:
            model: The SQLAlchemy model to create a scope for.
            root_alias: The aliased class to use as the root of the scope.

        Yields:
            A new transpiler instance with the sub-scope.
        """
        current_scope, sub_scope = self.scope, self.scope.sub(model, root_alias)
        try:
            self.scope = sub_scope
            yield self
        finally:
            self.scope = current_scope

    def _filter_to_expressions(
        self,
        dto_filter: GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]],
        override: ColumnElement[Any] | None = None,
        not_null_check: bool = False,
    ) -> list[ColumnElement[bool]]:
        """Converts a DTO filter to a list of SQLAlchemy expressions.

        Args:
            dto_filter: The DTO filter to convert.
            override: An optional column element to override the filter attribute.
            not_null_check: Whether to add a not-null check to the expressions.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = []
        attribute = override if override is not None else self.scope.aliased_attribute(dto_filter.field_node)
        expressions = dto_filter.to_expressions(self.dialect, attribute)
        if not_null_check:
            expressions.append(attribute.is_not(null()))
        return expressions

    def _gather_joins(self, tree: SQLAlchemyQueryNode, is_outer: bool = False) -> list[Join]:
        """Gathers all joins needed for a query tree.

        Args:
            tree: The query tree to gather joins from.
            is_outer: Whether to create outer joins.

        Returns:
            A list of join objects for the query tree.
        """
        joins: list[Join] = []
        for child in tree.iter_breadth_first():
            if child.value.is_computed or not child.value.is_relation or child.is_root:
                continue
            joins.append(self._join(child, is_outer=is_outer))
        return joins

    def _gather_conjonctions(
        self,
        query: Sequence[
            Filter[DeclarativeBase, QueryableAttribute[Any]]
            | AggregationFilter[DeclarativeBase, QueryableAttribute[Any]]
            | GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]
        ],
        not_null_check: bool = False,
    ) -> Conjunction:
        """Gathers all conjunctions from a sequence of filters.

        Args:
            query: A sequence of filters to gather conjunctions from.
            not_null_check: Whether to add not null checks to the expressions.

        Returns:
            A conjunction object containing the gathered expressions, joins and common join path.
        """
        bool_expressions: list[ColumnElement[bool]] = []
        joins: list[Join] = []
        common_join_path: list[SQLAlchemyQueryNode] = []
        node_path: list[SQLAlchemyQueryNode] = []

        for value in query:
            if isinstance(value, AggregationFilter):
                node_path = value.field_node.path_from_root()
                lateral_join, aggregation_expressions = self._aggregation_filter(value)
                if lateral_join is not None:
                    joins.append(lateral_join)
                bool_expressions.extend(aggregation_expressions)
            elif isinstance(value, GraphQLComparison):
                node_path = value.field_node.path_from_root()
                bool_expressions.extend(self._filter_to_expressions(value, not_null_check=not_null_check))
            else:
                conjunction = self._conjonctions(value, not_null_check)
                common_join_path = QueryNode.common_path(common_join_path, conjunction.common_join_path)
                joins.extend(conjunction.joins)
                if conjunction.expressions:
                    and_expression = and_(*conjunction.expressions)
                    bool_expressions.append(
                        and_expression.self_group() if conjunction.has_many_predicates() else and_expression
                    )
            if not isinstance(value, AggregationFilter):
                common_join_path = QueryNode.common_path(node_path, common_join_path)
        return Conjunction(bool_expressions, joins, common_join_path)

    def _conjonctions(
        self,
        query: Filter[DeclarativeBase, QueryableAttribute[Any]],
        allow_null: bool = False,
    ) -> Conjunction:
        """Processes a filter's AND, OR, and NOT conditions into a conjunction.

        Args:
            query: The filter to process.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A conjunction object containing the processed expressions, joins and common join path.
        """
        bool_expressions: list[ColumnElement[bool]] = []
        and_conjunction = self._gather_conjonctions(query.and_, allow_null)
        or_conjunction = self._gather_conjonctions(query.or_, allow_null)
        common_path = QueryNode.common_path(and_conjunction.common_join_path, or_conjunction.common_join_path)
        joins = [*and_conjunction.joins, *or_conjunction.joins]

        if query.not_:
            not_conjunction = self._gather_conjonctions([query.not_], not_null_check=True)
            common_path = [
                node
                for node in common_path
                if not any(not_node == node for not_node in not_conjunction.common_join_path)
            ]
            joins.extend(not_conjunction.joins)
            and_conjunction.expressions.append(not_(and_(*not_conjunction.expressions)))
        if and_conjunction.expressions:
            and_expression = and_(*and_conjunction.expressions)
            if or_conjunction.expressions and and_conjunction.has_many_predicates():
                and_expression = and_expression.self_group()
            bool_expressions.append(and_expression)
        if or_conjunction.expressions:
            or_expression = or_(*or_conjunction.expressions)
            if and_conjunction.expressions and or_conjunction.has_many_predicates():
                or_expression = or_expression.self_group()
            bool_expressions.append(or_expression)
        return Conjunction(bool_expressions, joins, common_path)

    def _aggregation_filter(
        self, aggregation: AggregationFilter[DeclarativeBase, QueryableAttribute[Any]]
    ) -> tuple[Join | None, list[ColumnElement[bool]]]:
        """Creates a join and filter expressions for an aggregation filter.

        Args:
            aggregation: The aggregation filter to process.

        Returns:
            A tuple containing:
                - The join object if a new join is needed, None otherwise.
                - A list of boolean expressions for the filter.
        """
        lateral_name = self.scope.key(self._aggregation_name_prefix)
        function_node = aggregation.field_node
        function_node_inspect = self.scope.inspect(function_node)
        aggregation_node = function_node.first_aggregate_parent()
        aggregated_alias: AliasedClass[Any] = aliased(function_node_inspect.mapper.class_)
        aggregated_alias_inspected = inspect(aggregated_alias)
        root_relation = self.scope.aliased_attribute(aggregation_node).of_type(aggregated_alias)
        functions = function_node_inspect.functions(aggregated_alias)
        bool_expressions: list[ColumnElement[bool]] = []

        if (function_column := self.scope.columns.get(function_node)) is not None:
            bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
            return None, bool_expressions

        if join_info := self._aggregation_joins.get(aggregation_node):
            for node, function in functions.items():
                _, created = join_info.upsert_column_to_subquery(function)
                function_column = self.scope.literal_column(join_info.name, self.scope.key(node))
                if created:
                    self.scope.columns[node] = function_column
                    self.scope.where_function_nodes.add(node)
                bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
            return None, bool_expressions

        for node in functions:
            function_column = self.scope.literal_column(lateral_name, self.scope.key(node))
            bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
            self.scope.columns[node] = function_column
            self.scope.where_function_nodes.add(node)

        statement = (
            select(*functions.values())
            .where(root_relation.expression)
            .select_from(aggregated_alias_inspected)
            .lateral(lateral_name)
        )
        join_info = AggregationJoin(
            join=statement,
            onclause=true(),
            node=aggregation_node,
            subquery_alias=aggregated_alias,
        )
        self._aggregation_joins[aggregation_node] = join_info

        return join_info, bool_expressions

    def _upsert_aggregations(
        self, aggregation_node: SQLAlchemyQueryNode, existing_joins: list[Join]
    ) -> tuple[list[NamedColumn[Any]], Join | None]:
        """Upserts aggregations.

        Args:
            aggregation_node: SQLAlchemyQueryNode
            existing_joins: list[_Join]

        Returns:
            tuple[list[NamedColumn[Any]], _Join | None]:
        """
        node_inspect = self.scope.inspect(aggregation_node)
        functions: dict[SQLAlchemyQueryNode, ColumnElement[Any]] = {}
        function_columns: list[NamedColumn[Any]] = []
        new_join: Join | None = None
        existing_join = next(
            (join for join in existing_joins if isinstance(join, AggregationJoin) and join.node == aggregation_node),
            None,
        )
        alias = existing_join.subquery_alias if existing_join else aliased(node_inspect.mapper)
        for child_inspect in node_inspect.children:
            child_functions = child_inspect.functions(alias)
            for node in set(child_functions) & set(self.scope.columns):
                child_functions.pop(node)
                function_columns.append(self.scope.columns[node])
            functions.update(child_functions)
        if not functions:
            return function_columns, None
        if existing_join:
            for node, function in functions.items():
                _, created = existing_join.upsert_column_to_subquery(function)
                function_column = self.scope.literal_column(existing_join.name, self.scope.key(node))
                if created:
                    self.scope.columns[node] = function_column
                function_columns.append(function_column)
        else:
            new_join = self._aggregation_join(aggregation_node, functions.values(), alias)
            for node in functions:
                function_column = self.scope.literal_column(new_join.name, self.scope.key(node))
                self.scope.columns[node] = function_column
                function_columns.append(function_column)

        return function_columns, new_join

    def _root_alias_as_subquery(
        self, selection_tree: SQLAlchemyQueryNode, order_by_nodes: list[SQLAlchemyOrderByNode], components: Query
    ) -> AliasedClass[DeclarativeT]:
        """Root alias as subquery.

        Args:
            selection_tree: SQLAlchemyQueryNode
            order_by_nodes: list[SQLAlchemyOrderByNode]
            components: _Query
            query_hooks: dict[SQLAlchemyQueryNode, QueryHook[Any]] | None

        Returns:
            AliasedClass[AnyDeclarative]:
        """
        subquery_name = self.scope.model.__tablename__
        root_insepcted = inspect(self._sub_query_root_alias)
        statement = select(root_insepcted).options(raiseload("*"))
        statement = statement.with_only_columns(
            *[self.scope.columns[node] for node in self.scope.referenced_function_nodes],
            *self.scope.inspect(selection_tree).selection(self._sub_query_root_alias),
            *[self.scope.aliased_attribute(node) for node in order_by_nodes if not node.value.is_computed],
        )

        for function_node in self.scope.referenced_function_nodes:
            self.scope.columns[function_node] = self.scope.literal_column(subquery_name, self.scope.key(function_node))

        statement = components.statement(statement)

        for hook_callable in self._query_hooks[selection_tree.root]:
            hook = hook_callable(statement, self.scope.root_alias)
            statement = hook.statement

        return aliased(class_mapper(self.scope.model), statement.subquery(subquery_name), name=subquery_name)

    def _apply_load_options(self, statement: Select[tuple[DeclarativeT]], node: SQLAlchemyQueryNode) -> _AbstractLoad:
        """Applies the load options to the statement for the given node.

        Load is applied based on whether it's a relation or not.
        If it's a relation, it calls itself recursively for
        each child node and applies the load options to the statement.

        Args:
            statement: The statement to be modified
            node: The node to apply the load options for
            query_hooks: The query hooks to use for the node and its children

        Returns:
            The modified statement with the load options applied
        """
        columns = self.scope.inspect(node).columns_or_ids()
        self.scope.selected_columns.extend(columns)
        eager_options: list[_AbstractLoad] = []
        load = contains_eager(self.scope.aliased_attribute(node))
        if columns:
            load = load.options(load_only(*columns))
            eager_options = [load_only(*columns)]

        for hook_callable in self._query_hooks[node]:
            hook = hook_callable(statement, self.scope.alias_from_relation_node(node, "target"))
            statement = hook.statement
            eager_options.extend(hook.load_options)
        load = load.options(*eager_options)

        for child in node.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            if options := self._apply_load_options(statement, child):
                load = load.options(options)
        return load

    def _root_aggregation_functions(self, selection_tree: SQLAlchemyQueryNode) -> list[Label[Any]]:
        """Build a list of root aggregations, given an SQLAlchemyQueryNode representing the selection tree.

        :param selection_tree: The selection tree to build root aggregations from
        :return: A list of Labels representing the root aggregations
        """
        aggregation_tree = selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        if not aggregation_tree:
            return []
        # Apply over() on each root aggregation function
        return [
            function
            for child in aggregation_tree.children
            for function in self.scope.inspect(child)
            .functions(self.scope.root_alias, lambda func: func.over())
            .values()
        ]

    def _join(self, node: SQLAlchemyQueryNode, is_outer: bool = False) -> Join:
        """Creates a join object for a query node.

        Args:
            node: The query node to create a join for.
            is_outer: Whether to create an outer join.

        Returns:
            A join object containing the join information.
        """
        node_inspect = self.scope.inspect(node)
        aliased_attribute = self.scope.aliased_attribute(node)
        relation_filter = node.relation_filter
        if not relation_filter:
            return Join(aliased_attribute, node=node, is_outer=is_outer)
        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        mapper: Mapper[Any] = relationship.mapper.mapper
        alias = aliased(mapper, flat=True)
        inspect_alias = inspect(alias)
        root_relation = aliased_attribute.of_type(inspect_alias)
        name = self.scope.key(node)
        base_statement = select(inspect(alias)).with_only_columns(*node_inspect.selection(alias))
        with self._sub_scope(mapper.class_, alias):
            query = self._build_query(
                QueryGraph(self.scope, order_by=relation_filter.order_by or []),
                limit=relation_filter.limit,
                offset=relation_filter.offset,
            )
        statement = query.statement(base_statement).where(root_relation).lateral(name)
        lateral_alias = aliased(relationship.entity.mapper, statement, name=name, flat=True)
        self.scope.set_relation_alias(node, "target", lateral_alias)
        return Join(statement, node=node, is_outer=is_outer, onclause=true())

    def _aggregation_join(
        self,
        node: SQLAlchemyQueryNode,
        function_columns: Iterable[ColumnElement[Any]],
        alias: AliasedClass[Any],
    ) -> AggregationJoin:
        """Creates an aggregation join object for a query node.

        Args:
            node: The query node to create an aggregation join for.
            function_columns: The columns to include in the aggregation.
            alias: The alias to use for the joined table.

        Returns:
            An aggregation join object containing the join information.
        """
        lateral_name = self.scope.key(self._aggregation_name_prefix)
        root_relation = self.scope.aliased_attribute(node).of_type(inspect(alias))
        lateral_statement = select(*function_columns).where(root_relation).lateral(lateral_name)
        return AggregationJoin(join=lateral_statement, onclause=true(), node=node, subquery_alias=alias)

    def _where(
        self,
        query_filter: Filter[DeclarativeBase, QueryableAttribute[Any]],
        allow_null: bool = False,
    ) -> Where:
        """Creates WHERE expressions and joins from a filter.

        Args:
            query_filter: The filter to create expressions from.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A tuple containing:
                - List of boolean expressions for the WHERE clause
                - List of joins needed for the expressions
        """
        conjunction = self._conjonctions(query_filter, allow_null)
        return Where(
            conjunction,
            [
                *conjunction.joins,
                *[
                    self._join(node)
                    for node in conjunction.common_join_path
                    if not node.is_root and node.value.is_relation
                ],
            ],
        )

    def _order_by(self, order_by_nodes: list[SQLAlchemyOrderByNode], existing_joins: list[Join]) -> OrderBy:
        """Creates ORDER BY expressions and joins from a list of nodes.

        Args:
            order_by_nodes: The nodes to create order by expressions from.
            existing_joins: List of existing joins to check for reuse.

        Returns:
            A tuple containing:
                - List of unary expressions for the ORDER BY clause
                - List of new joins needed for the expressions
        """
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        joins: list[Join] = []
        seen_aggregation_nodes: set[SQLAlchemyOrderByNode] = set()

        for node in order_by_nodes:
            if node.value.is_function_arg and node.first_aggregate_parent() in seen_aggregation_nodes:
                continue
            if node.value.is_function:
                self.scope.order_by_function_nodes.add(node)
            if node.order_by is None:
                msg = "Missing order by value"
                raise TranspilingError(msg)
            if node.value.is_function_arg or node.value.is_function:
                aggregation_node = node.first_aggregate_parent()
                function_columns, new_join = self._upsert_aggregations(aggregation_node, existing_joins)
                columns.extend([(function_column, node.order_by) for function_column in function_columns])
                seen_aggregation_nodes.add(aggregation_node)
                if new_join:
                    joins.append(new_join)
            else:
                columns.append((self.scope.aliased_attribute(node), node.order_by))
        return OrderBy(columns, joins)

    def _select(self, selection_tree: SQLAlchemyQueryNode) -> tuple[Select[tuple[DeclarativeT]], list[Join]]:
        aggregation_joins: list[Join] = []
        statement = self._base_statement()
        root_columns = self.scope.inspect(selection_tree).columns_or_ids()
        self.scope.selected_columns.extend(root_columns)
        for node in selection_tree.iter_depth_first():
            if node.value.is_aggregate:
                function_columns, new_join = self._upsert_aggregations(node, aggregation_joins)
                statement = statement.add_columns(*function_columns)
                self.scope.selected_columns.extend(function_columns)
                if new_join:
                    aggregation_joins.append(new_join)
        # Only load selected root columns + those of child relations
        root_options = [load_only(*root_columns)] if root_columns else []

        for hook_callable in self._query_hooks[selection_tree.root]:
            hook = hook_callable(statement, self.scope.root_alias)
            statement = hook.statement
            root_options.extend(hook.load_options)

        statement = statement.options(raiseload("*"), *root_options)

        for child in selection_tree.children:
            if not child.value.is_relation:
                continue
            statement = statement.options(self._apply_load_options(statement, child))

        return statement, aggregation_joins

    def _build_query(
        self,
        query_graph: QueryGraph[DeclarativeT],
        selection_tree: SQLAlchemyQueryNode | None = None,
        limit: int | None = None,
        offset: int | None = None,
        allow_null: bool = False,
    ) -> Query:
        joins: list[Join] = []
        subquery_join_nodes: set[SQLAlchemyQueryNode] = set()  # Track nodes already joined
        has_root_subquery: bool = False  # Flag for root-level pagination
        query = Query(limit=limit, offset=offset)

        if self.scope.is_root and (limit is not None or offset is not None):
            has_root_subquery = True
            self.scope.replace(alias=self._sub_query_root_alias)

        if query_graph.query_filter:
            query.where = self._where(query_graph.query_filter, allow_null)
            joins.extend(query.where.joins)
            subquery_join_nodes = {join.node for join in query.where.joins}

        if query_graph.order_by_tree:
            query.order_by = self._order_by(query_graph.order_by_nodes, joins)
            joins.extend(query.order_by.joins)

        if query_graph.subquery_join_tree:
            joins.extend(
                [
                    join
                    for join in self._gather_joins(query_graph.subquery_join_tree, is_outer=True)
                    if join.node not in subquery_join_nodes
                ]
            )

        if has_root_subquery:
            subquery_alias = self._root_alias_as_subquery(
                query_graph.resolved_selection_tree, query_graph.order_by_nodes, dataclasses.replace(query, joins=joins)
            )
            self.scope.replace(alias=subquery_alias)
            limit, offset = None, None
            query.distinct_on = DistinctOn(query_graph)
            query.joins = self._gather_joins(query_graph.root_join_tree, is_outer=True)
            query.order_by = self._order_by(query_graph.order_by_nodes, query.joins)
            query.joins.extend(query.order_by.joins)
            if query.where:
                query.where.clear_expressions()
        else:
            query.distinct_on = DistinctOn(query_graph)
            query.joins = joins + [
                join
                for join in self._gather_joins(query_graph.root_join_tree, is_outer=True)
                if join.node not in subquery_join_nodes
            ]

        # Process root-level aggregations using window functions if requested
        if selection_tree and selection_tree.query_metadata.root_aggregations:
            query.root_aggregation_functions = self._root_aggregation_functions(selection_tree)

        return query

    def executor(
        self,
        selection_tree: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        executor_cls: type[QueryExecutorT] = SyncQueryExecutor,
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
            statement_type: Type of statement to generate ('lambda' by default).
            allow_null: Whether to allow null values in filter conditions.
            root_aggregations: Whether to include aggregations at the root level.
            query_hooks: Dictionary mapping nodes to query modification functions.
            executor_cls: Executor type to return
            execution_options: Options for statement execution

        Returns:
            A QueryExecutor instance that can execute the built query.

        Example:
            ```python
            # Create an executor that selects user data with filtering and ordering
            executor = transpiler.executor(
                selection_tree=user_fields_tree,
                dto_filter=BooleanFilterDTO(field="age", op="gt", value=18),
                order_by=[OrderByDTO(field="name", direction="ASC")],
                limit=10
            )
            results = await executor.execute()
            ```
        """
        query_graph = QueryGraph(
            self.scope,
            selection_tree=selection_tree,
            dto_filter=dto_filter,
            order_by=order_by or [],
            distinct_on=distinct_on or [],
        )
        query = self._build_query(query_graph, selection_tree, limit, offset, allow_null)
        statement, aggregation_joins = self._select(query_graph.resolved_selection_tree)
        query.joins.extend(aggregation_joins)
        statement = query.statement(statement)

        return executor_cls(
            base_statement=statement,
            apply_unique=query.joins_have_many,
            root_aggregation_functions=query.root_aggregation_functions,
            scope=self.scope,
        )

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.scope.model}>"
