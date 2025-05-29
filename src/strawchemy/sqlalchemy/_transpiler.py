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
from typing import TYPE_CHECKING, Any, Generic, Self, cast, override

from sqlalchemy import Dialect, Label, Select, and_, func, inspect, not_, null, or_, select, true
from sqlalchemy.orm import Mapper, RelationshipProperty, aliased, class_mapper, contains_eager, load_only, raiseload
from sqlalchemy.sql.elements import ColumnElement
from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.strawberry.dto import (
    AggregationFilter,
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    OrderByDTO,
    OrderByEnum,
    OrderByRelationFilterDTO,
    QueryNode,
)
from strawchemy.strawberry.filters import GraphQLComparison

from ._executor import SyncQueryExecutor
from ._query import (
    AggregationJoin,
    Conjunction,
    DistinctOn,
    HookApplier,
    Join,
    OrderBy,
    Query,
    QueryGraph,
    SubqueryBuilder,
    Where,
)
from ._scope import QueryScope
from .exceptions import TranspilingError
from .inspector import SQLAlchemyGraphQLInspector
from .typing import DeclarativeT, OrderBySpec, QueryExecutorT

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql.elements import NamedColumn
    from strawchemy.strawberry.typing import QueryNodeType
    from strawchemy.typing import SupportedDialect

    from .hook import QueryHook

__all__ = ("QueryTranspiler",)


class QueryTranspiler(Generic[DeclarativeT]):
    """Transpiles a GraphQL query into a SQLAlchemy query."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        statement: Select[tuple[DeclarativeT]] | None = None,
        scope: QueryScope[DeclarativeT] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
    ) -> None:
        supported_dialect = cast("SupportedDialect", dialect.name)
        self._inspector = SQLAlchemyGraphQLInspector(supported_dialect, [model.registry])
        self._aggregation_prefix: str = "aggregation"
        self._aggregation_joins: dict[QueryNodeType, AggregationJoin] = {}
        self._statement = statement
        self._deterministic_ordering = deterministic_ordering
        self.dialect = dialect
        self.scope = scope or QueryScope(model, supported_dialect, inspector=self._inspector)

        self._hook_applier = HookApplier(self.scope, query_hooks or defaultdict(list))

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
        dto_filter: GraphQLComparison,
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

    def _gather_joins(self, tree: QueryNodeType, is_outer: bool = False) -> list[Join]:
        """Gathers all joins needed for a query tree.

        Args:
            tree: The query tree to gather joins from.
            is_outer: Whether to create outer joins.

        Returns:
            A list of join objects for the query tree.
        """
        joins: list[Join] = [
            self._join(child, is_outer=is_outer)
            for child in tree.iter_breadth_first()
            if not child.value.is_computed and child.value.is_relation and not child.is_root
        ]
        return joins

    def _gather_conjonctions(
        self,
        query: Sequence[Filter | AggregationFilter | GraphQLComparison],
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
        common_join_path: list[QueryNodeType] = []
        node_path: list[QueryNodeType] = []

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

    def _conjonctions(self, query: Filter, allow_null: bool = False) -> Conjunction:
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
                node for node in common_path if all(not_node != node for not_node in not_conjunction.common_join_path)
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

    def _aggregation_filter(self, aggregation: AggregationFilter) -> tuple[Join | None, list[ColumnElement[bool]]]:
        """Creates a join and filter expressions for an aggregation filter.

        Args:
            aggregation: The aggregation filter to process.

        Returns:
            A tuple containing:
                - The join object if a new join is needed, None otherwise.
                - A list of boolean expressions for the filter.
        """
        aggregation_name = self.scope.key(self._aggregation_prefix)
        aggregation_node_inspect = self.scope.inspect(aggregation.field_node)
        aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
        aggregated_alias: AliasedClass[Any] = aliased(aggregation_node_inspect.mapper.class_)
        aggregated_alias_inspected = inspect(aggregated_alias)
        root_relation = self.scope.aliased_attribute(aggregation_node).of_type(aggregated_alias)
        bool_expressions: list[ColumnElement[bool]] = []

        # The aggregation column already exists, we just need to add the filter expression
        if (function_column := self.scope.columns.get(aggregation.field_node)) is not None:
            bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
            return None, bool_expressions

        # If an existing lateral join exists, add the aggregation column to it
        if join := self._aggregation_joins.get(aggregation_node):
            function_node, function = aggregation_node_inspect.filter_function(
                join.subquery_alias, distinct=aggregation.distinct
            )
            _, created = join.upsert_column_to_subquery(function)
            function_column = self.scope.literal_column(join.name, self.scope.key(function_node))
            if created:
                self.scope.columns[function_node] = function_column
                self.scope.where_function_nodes.add(function_node)
            bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
            return None, bool_expressions

        function_node, function = aggregation_node_inspect.filter_function(
            aggregated_alias, distinct=aggregation.distinct
        )
        function_column = self.scope.literal_column(aggregation_name, self.scope.key(function_node))
        bool_expressions.extend(aggregation.predicate.to_expressions(self.dialect, function_column))
        self.scope.columns[function_node] = function_column
        self.scope.where_function_nodes.add(function_node)

        if self._inspector.db_features.supports_lateral:
            statement = select(function).where(root_relation.expression).select_from(aggregated_alias_inspected)
            join = AggregationJoin(
                target=statement.lateral(aggregation_name),
                onclause=true(),
                node=aggregation_node,
                subquery_alias=aggregated_alias,
            )
        else:
            join = self._aggregation_cte_join(
                node=aggregation_node,
                alias=aggregated_alias,
                statement=select(function).select_from(aggregated_alias_inspected),
                cte_name=aggregation_name,
            )

        self._aggregation_joins[aggregation_node] = join
        return join, bool_expressions

    def _upsert_aggregations(
        self, aggregation_node: QueryNodeType, existing_joins: list[Join]
    ) -> tuple[list[NamedColumn[Any]], Join | None]:
        """Upserts aggregations.

        Args:
            aggregation_node: QueryNodeType
            existing_joins: list[_Join]

        Returns:
            tuple[list[NamedColumn[Any]], _Join | None]:
        """
        node_inspect = self.scope.inspect(aggregation_node)
        functions: dict[QueryNodeType, ColumnElement[Any]] = {}
        function_columns: list[NamedColumn[Any]] = []
        new_join: Join | None = None
        existing_join = next(
            (join for join in existing_joins if isinstance(join, AggregationJoin) and join.node == aggregation_node),
            None,
        )
        alias = existing_join.subquery_alias if existing_join else aliased(node_inspect.mapper)
        for child_inspect in node_inspect.children:
            child_functions = child_inspect.output_functions(alias)
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
            if self._inspector.db_features.supports_lateral:
                new_join = self._aggregation_lateral_join(aggregation_node, functions.values(), alias)
            else:
                new_join = self._aggregation_cte_join(
                    node=aggregation_node,
                    alias=alias,
                    statement=select(*functions.values()),
                    cte_name=self.scope.key(self._aggregation_prefix),
                )
            for node in functions:
                function_column = self.scope.literal_column(new_join.name, self.scope.key(node))
                self.scope.columns[node] = function_column
                function_columns.append(function_column)

        return function_columns, new_join

    def _select_child(
        self, statement: Select[tuple[DeclarativeT]], node: QueryNodeType
    ) -> tuple[Select[tuple[DeclarativeT]], _AbstractLoad]:
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
        columns, column_transforms = self.scope.inspect(node).columns()
        for column_transform in column_transforms:
            statement = statement.add_columns(column_transform.attribute)
        eager_options: list[_AbstractLoad] = []
        load = contains_eager(self.scope.aliased_attribute(node))
        if columns:
            eager_options = [load_only(*columns)]

        node_alias = self.scope.alias_from_relation_node(node, "target")
        statement, hook_options = self._hook_applier.apply(statement, node, node_alias, "undefer")
        eager_options.extend(hook_options)
        load = load.options(*eager_options)

        for child in node.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            statement, column_options = self._select_child(statement, child)
            if column_options:
                load = load.options(column_options)
        return statement, load

    def _root_aggregation_functions(self, selection_tree: QueryNodeType) -> list[Label[Any]]:
        """Build a list of root aggregations, given an QueryNodeType representing the selection tree.

        :param selection_tree: The selection tree to build root aggregations from
        :return: A list of Labels representing the root aggregations
        """
        if aggregation_tree := selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY):
            return [
                function
                for child in aggregation_tree.children
                for function in self.scope.inspect(child)
                .output_functions(self.scope.root_alias, lambda func: func.over())
                .values()
            ]
        return []

    def _join(self, node: QueryNodeType, is_outer: bool = False) -> Join:
        """Creates a join object for a query node.

        Args:
            node: The query node to create a join for.
            is_outer: Whether to create an outer join.

        Returns:
            A join object containing the join information.
        """
        aliased_attribute = self.scope.aliased_attribute(node)
        relation_filter = node.metadata.data.relation_filter
        if not relation_filter:
            return Join(aliased_attribute, node=node, is_outer=is_outer)
        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        target_mapper: Mapper[Any] = relationship.mapper.mapper
        target_alias = aliased(target_mapper, flat=True)
        order_by = relation_filter.order_by if isinstance(relation_filter, OrderByRelationFilterDTO) else ()
        with self._sub_scope(target_mapper.class_, target_alias):
            query_graph = QueryGraph(self.scope, order_by=order_by)
            query = self._build_query(query_graph, limit=relation_filter.limit, offset=relation_filter.offset)
        if self._inspector.db_features.supports_lateral:
            join = self._lateral_join(node, target_alias, query, is_outer)
        else:
            join = self._cte_join(node, target_alias, query, is_outer)
        join.order_nodes = query_graph.order_by_nodes
        return join

    def _lateral_join(self, node: QueryNodeType, target_alias: AliasedClass[Any], query: Query, is_outer: bool) -> Join:
        target_insp = inspect(target_alias)
        aliased_attribute = self.scope.aliased_attribute(node)
        node_inspect = self.scope.inspect(node)
        name = self.scope.key(node)
        root_relation = aliased_attribute.of_type(target_insp)
        base_statement = select(target_insp).with_only_columns(*node_inspect.selection(target_alias))
        statement = query.statement(base_statement).where(root_relation).lateral(name)
        lateral_alias = aliased(target_insp.mapper, statement, name=name, flat=True)
        self.scope.set_relation_alias(node, "target", lateral_alias)
        return Join(statement, node=node, is_outer=is_outer, onclause=true())

    def _cte_join(self, node: QueryNodeType, target_alias: AliasedClass[Any], query: Query, is_outer: bool) -> Join:
        aliased_attribute = self.scope.aliased_attribute(node)
        remote_fks = self.scope.inspect(node).foreign_key_columns("target", target_alias)
        rank_column: Label[int] | None = None
        if query.order_by or query.limit is not None or query.offset is not None:
            rank_column = (
                func.dense_rank()
                .over(partition_by=remote_fks, order_by=query.order_by.expressions if query.order_by else None)
                .label(name="rank")
            )
        name = self.scope.key(node)
        # Remove limit/offset in CTE as it's applied in the WHERE clause of the main query
        query_wihtout_limit_offset = dataclasses.replace(query, offset=None, limit=None)
        node_inspect = self.scope.inspect(node)
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
        self.scope.set_relation_alias(node, "target", cte_alias)
        limit_offset_condition: list[ColumnElement[bool]] = []
        if rank_column is not None:
            rank_column = self.scope.literal_column(name, rank_column.name)
            if query.offset is not None:
                limit_offset_condition.append(rank_column > query.offset)
            if query.limit is not None:
                limit_offset_condition.append(
                    rank_column <= (query.offset + query.limit if query.offset else query.limit)
                )
        return Join(statement, node, onclause=and_(aliased_attribute, *limit_offset_condition), is_outer=is_outer)

    def _aggregation_lateral_join(
        self, node: QueryNodeType, function_columns: Iterable[ColumnElement[Any]], alias: AliasedClass[Any]
    ) -> AggregationJoin:
        """Creates an aggregation join object for a query node.

        Args:
            node: The query node to create an aggregation join for.
            function_columns: The columns to include in the aggregation.
            alias: The alias to use for the joined table.

        Returns:
            An aggregation join object containing the join information.
        """
        lateral_name = self.scope.key(self._aggregation_prefix)
        root_relation = self.scope.aliased_attribute(node).of_type(inspect(alias))
        lateral_statement = select(*function_columns).where(root_relation).lateral(lateral_name)
        return AggregationJoin(target=lateral_statement, onclause=true(), node=node, subquery_alias=alias)

    def _aggregation_cte_join(
        self, node: QueryNodeType, alias: AliasedClass[Any], statement: Select[Any], cte_name: str
    ) -> AggregationJoin:
        remote_fks = self.scope.inspect(node).foreign_key_columns("target", alias)
        cte_statement = (
            statement.add_columns(*remote_fks)
            .group_by(*remote_fks)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
            .cte(cte_name)
        )
        cte_alias = aliased(alias, cte_statement)
        return AggregationJoin(
            target=cte_alias,
            onclause=self.scope.aliased_attribute(node).of_type(cte_alias),
            node=node,
            subquery_alias=alias,
        )

    def _where(self, query_filter: Filter, allow_null: bool = False) -> Where:
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

    def _order_by(self, order_by_nodes: list[QueryNodeType], existing_joins: list[Join]) -> OrderBy:
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
        seen_aggregation_nodes: set[QueryNodeType] = set()

        for node in order_by_nodes:
            if (
                node.value.is_function_arg
                and node.find_parent(lambda node: node.value.is_aggregate, strict=True) in seen_aggregation_nodes
            ):
                continue
            if node.value.is_function:
                self.scope.order_by_function_nodes.add(node)
            if node.metadata.data.order_by is None:
                msg = "Missing order by value"
                raise TranspilingError(msg)
            if node.value.is_function_arg or node.value.is_function:
                first_aggregate_parent = node.find_parent(lambda node: node.value.is_aggregate, strict=True)
                function_columns, new_join = self._upsert_aggregations(first_aggregate_parent, existing_joins)
                columns.extend([(function_column, node.metadata.data.order_by) for function_column in function_columns])
                seen_aggregation_nodes.add(first_aggregate_parent)
                if new_join:
                    joins.append(new_join)
            else:
                columns.append((self.scope.aliased_attribute(node), node.metadata.data.order_by))
        if not columns and self._deterministic_ordering:
            pk_aliases = [
                pk_attribute.adapt_to_entity(inspect(self.scope.root_alias))
                for pk_attribute in self._inspector.pk_attributes(self.scope.model.__mapper__)
            ]
            columns.extend([(id_col, OrderByEnum.ASC) for id_col in pk_aliases])
        return OrderBy(self._inspector.db_features, columns, joins)

    def _select(self, selection_tree: QueryNodeType) -> tuple[Select[tuple[DeclarativeT]], list[Join]]:
        aggregation_joins: list[Join] = []
        statement = self._base_statement()
        root_columns, column_transforms = self.scope.inspect(selection_tree).columns()
        for column_transform in column_transforms:
            statement = statement.add_columns(column_transform.attribute)
        for node in selection_tree.iter_depth_first():
            if node.value.is_aggregate:
                function_columns, new_join = self._upsert_aggregations(node, aggregation_joins)
                statement = statement.add_columns(*function_columns)
                if new_join:
                    aggregation_joins.append(new_join)
        # Only load selected root columns + those of child relations
        root_options = [load_only(*root_columns)] if root_columns else []

        statement, hook_options = self._hook_applier.apply(
            statement, selection_tree.root, self.scope.root_alias, "undefer"
        )
        root_options.extend(hook_options)

        for child in selection_tree.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            statement, options = self._select_child(statement, child)
            root_options.append(options)

        statement = statement.options(raiseload("*"), *root_options)
        return statement, aggregation_joins

    def _use_distinct_rank(self, query_graph: QueryGraph[DeclarativeT]) -> bool:
        if self._inspector.db_features.supports_distinct_on:
            return bool(query_graph.distinct_on and (query_graph.order_by_tree or self._deterministic_ordering))
        return bool(query_graph.distinct_on)

    def _relation_order_by(self, query_graph: QueryGraph[DeclarativeT], query: Query) -> list[OrderBySpec]:
        selected_tree = query_graph.resolved_selection_tree()
        order_by_spec: list[OrderBySpec] = []
        for join in sorted(query.joins):
            if (
                isinstance(join, AggregationJoin)
                or join.node in query_graph.order_by_nodes
                or not selected_tree.find_child(
                    lambda node, _join=join: node.value.model_field is _join.node.value.model_field
                )
            ):
                continue
            if not join.order_nodes and self._deterministic_ordering:
                order_by_spec.extend(
                    [(attribute, OrderByEnum.ASC) for attribute in self.scope.aliased_id_attributes(join.node)]
                )
            elif join.order_nodes:
                order_by_spec.extend(
                    [
                        (self.scope.literal_column(join.name, node.value.model_field_name), node.metadata.data.order_by)
                        for node in join.order_nodes
                        if node.metadata.data.order_by
                    ]
                )
        return order_by_spec

    def _build_query(
        self,
        query_graph: QueryGraph[DeclarativeT],
        limit: int | None = None,
        offset: int | None = None,
        allow_null: bool = False,
    ) -> Query:
        joins: list[Join] = []
        subquery_join_nodes: set[QueryNodeType] = set()
        distinct_on_rank = self._use_distinct_rank(query_graph)
        query = Query(
            self._inspector.db_features,
            limit=limit,
            offset=offset,
            distinct_on=DistinctOn(query_graph),
            use_distinct_on=not distinct_on_rank,
        )
        subquery_needed = self.scope.is_root and (limit is not None or offset is not None or distinct_on_rank)
        subquery_builder = SubqueryBuilder(self.scope, self._hook_applier, self._inspector.db_features)

        if subquery_needed:
            self.scope.replace(alias=subquery_builder.alias)

        if query_graph.query_filter:
            query.where = self._where(query_graph.query_filter, allow_null)
            joins.extend(query.where.joins)
            subquery_join_nodes = {join.node for join in query.where.joins}

        if query_graph.order_by_tree or self._deterministic_ordering:
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

        if subquery_needed:
            subquery_alias = subquery_builder.build(query_graph, dataclasses.replace(query, joins=joins))
            self.scope.replace(alias=subquery_alias)
            query.offset = None
            query.joins = self._gather_joins(query_graph.root_join_tree, is_outer=True)
            query.order_by = self._order_by(query_graph.order_by_nodes, query.joins)
            query.joins.extend(query.order_by.joins)
            if distinct_on_rank:
                query.where = Where.from_expressions(subquery_builder.distinct_on_condition())
            elif query.where:
                query.where.clear_expressions()
        else:
            query.joins = joins + [
                join
                for join in self._gather_joins(query_graph.root_join_tree, is_outer=True)
                if join.node not in subquery_join_nodes
            ]

        # Add relation ORDER BY columns
        if query.order_by:
            query.order_by.columns.extend(self._relation_order_by(query_graph, query))

        # Process root-level aggregations using window functions if requested
        if query_graph.selection_tree and query_graph.selection_tree.graph_metadata.metadata.root_aggregations:
            query.root_aggregation_functions = self._root_aggregation_functions(query_graph.selection_tree)

        return query

    def select_executor(
        self,
        selection_tree: QueryNodeType | None = None,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
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
        query = self._build_query(query_graph, limit, offset, allow_null)
        statement, aggregation_joins = self._select(query_graph.resolved_selection_tree())
        query.joins.extend(aggregation_joins)
        statement = query.statement(statement)

        return executor_cls(
            base_statement=statement,
            apply_unique=query.joins_have_many,
            root_aggregation_functions=query.root_aggregation_functions,
            scope=self.scope,
            execution_options=execution_options,
        )

    def filter_expressions(self, dto_filter: BooleanFilterDTO) -> list[ColumnElement[bool]]:
        query_graph = QueryGraph(self.scope, dto_filter=dto_filter)
        query = self._build_query(query_graph)
        return query.where.expressions if query.where else []

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.scope.model}>"
