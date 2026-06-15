"""Transpiles a GraphQL query into a SQLAlchemy query.

This module contains the QueryTranspiler class, which is responsible for
converting a GraphQL query into a SQLAlchemy query.

Classes:
    QueryTranspiler: Transpiles a GraphQL query into a SQLAlchemy query.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy import Dialect, Label, Select, and_, inspect, not_, null, or_, select, true
from sqlalchemy.orm import Mapper, RelationshipProperty, aliased, class_mapper, contains_eager, load_only, raiseload
from typing_extensions import Self, override

from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.strawberry import (
    AggregationFilter,
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    OrderByDTO,
    OrderByEnum,
    OrderByRelationFilterDTO,
    QueryNode,
    decompose_order_by,
)
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.repository.typing import DeclarativeT, OrderBySpec, QueryExecutorT
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._executor import SyncQueryExecutor
from strawchemy.transpiler._query import (
    AggregationJoin,
    AggregationSpec,
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
from strawchemy.transpiler._scope import QueryScope
from strawchemy.transpiler._strategies import select_join_strategy

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql.elements import NamedColumn

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
        scope: QueryScope[DeclarativeT] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> None:
        """Initializes the QueryTranspiler.

        Args:
            model: The SQLAlchemy model to transpile queries for.
            dialect: The SQLAlchemy dialect to use.
            statement: An optional base SQLAlchemy statement to build upon.
            scope: An optional existing QueryScope.
            query_hooks: Optional hooks to apply during query transpilation.
            deterministic_ordering: Whether to ensure deterministic ordering of results.
            default_order_by: Default ordering applied when the client supplies no order.
                Each expression must reference a mapped column of the root model; validated on first use.
        """
        supported_dialect = cast("SupportedDialect", dialect.name)

        self._inspector = SQLAlchemyGraphQLInspector(supported_dialect, [model.registry])
        self._join_strategy = select_join_strategy(self._inspector.db_features)
        self._aggregation_joins: dict[QueryNodeType, AggregationJoin] = {}
        self._aggregation_specs_by_node: dict[QueryNodeType, AggregationSpec] = {}
        self._emitted_aggregation_joins: set[QueryNodeType] = set()
        self._statement = statement
        self._deterministic_ordering = deterministic_ordering
        self._default_order_by: list[OrderByExpr] = list(default_order_by or [])
        self._filter_in_subquery = False

        self.dialect = dialect
        self.scope = scope or QueryScope(model, supported_dialect, inspector=self._inspector)

        self._hook_applier = HookApplier(self.scope, query_hooks or defaultdict(list))

    def _apply_filter_statement(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[Any]
    ) -> Select[tuple[DeclarativeT]]:
        """Joins the `filter_statement` subquery to `alias` on primary-key equality.

        Restricts `statement` to rows that survive `filter_statement` as a semi-join
        (no columns selected from the filter subquery). Reused by both the outer query
        and the pagination/distinct subquery so OFFSET/LIMIT count only filter-visible
        rows.

        Args:
            statement: The select statement to restrict.
            alias: The root alias whose PK columns are matched against the filter subquery.

        Returns:
            The statement joined to the filter subquery on PK equality.
        """
        assert self._statement is not None
        root_mapper = class_mapper(self.scope.model)
        pk_attributes = self._inspector.pk_attributes(root_mapper)
        # Only PK columns are needed for the join, so avoid selecting the rest.
        filter_alias = self._statement.with_only_columns(*pk_attributes).subquery().alias()
        on_clause = and_(*[getattr(alias, attr.key) == filter_alias.c[attr.key] for attr in pk_attributes])
        return statement.join(filter_alias, onclause=on_clause)

    def _base_statement(self) -> Select[tuple[DeclarativeT]]:
        """Creates the base select statement for the query.

        Joins the `filter_statement` (if any) to the root alias on PK equality —
        unless that join was already pushed into the pagination/distinct subquery,
        in which case the root alias is the already scoped subquery and must not be re-joined.

        Returns:
            The base SQLAlchemy Select statement.
        """
        statement = select(self.scope.root_alias)
        if self._statement is not None and not self._filter_in_subquery:
            return self._apply_filter_statement(statement, self.scope.root_alias)
        return statement

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

    def _aggregation_specs(self, query_graph: QueryGraph[DeclarativeT]) -> dict[QueryNodeType, AggregationSpec]:
        """Collects one :class:`AggregationSpec` per aggregation node from the query graph.

        Function expressions are accumulated in a fixed source order — filter, then
        order-by, then selection — and deduplicated per aggregation node by their
        function node, so the same function referenced by several sources yields a
        single built column. The accumulation order is preserved to keep the built
        subquery's column order stable.

        Args:
            query_graph: The graph representation of the query being built.

        Returns:
            A mapping of aggregation node to its accumulated spec, in first-seen order.
        """
        specs: dict[QueryNodeType, AggregationSpec] = {}

        # Filter source
        if query_graph.query_filter is not None:
            for aggregation in self._iter_aggregation_filters(query_graph.query_filter):
                aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
                spec = self._aggregation_spec(specs, aggregation_node)
                function_node, function = self.scope.inspect(aggregation.field_node).filter_function(
                    spec.alias, distinct=aggregation.distinct
                )
                if function_node not in spec.functions:
                    spec.functions[function_node] = function

        # Order-by then selection sources
        order_by_aggregations = (
            node.find_parent(lambda node: node.value.is_aggregate, strict=True)
            for node in query_graph.order_by_nodes
            if node.value.is_function or node.value.is_function_arg
        )
        selection_aggregations = (
            node for node in query_graph.resolved_selection_tree().iter_depth_first() if node.value.is_aggregate
        )
        for aggregation_node in (*order_by_aggregations, *selection_aggregations):
            spec = self._aggregation_spec(specs, aggregation_node)
            for child_inspect in self.scope.inspect(aggregation_node).children:
                for function_node, function in child_inspect.output_functions(spec.alias).items():
                    if function_node not in spec.functions:
                        spec.functions[function_node] = function

        return specs

    def _aggregation_spec(self, specs: dict[QueryNodeType, AggregationSpec], node: QueryNodeType) -> AggregationSpec:
        """Gets the spec for an aggregation node, creating and recording it if absent.

        Args:
            specs: The accumulating mapping of aggregation node to spec.
            node: The aggregation node to get or create a spec for.

        Returns:
            The existing or newly created spec for the node.
        """
        spec = specs.get(node)
        if spec is None:
            spec = specs[node] = AggregationSpec.create(node, self.scope)
        return spec

    @staticmethod
    def _iter_aggregation_filters(query_filter: Filter) -> Iterator[AggregationFilter]:
        """Yields every :class:`AggregationFilter` in a filter tree in traversal order.

        Args:
            query_filter: The processed filter to walk.

        Yields:
            Each aggregation filter found under the AND, OR and NOT branches.
        """
        for value in query_filter.and_:
            if isinstance(value, AggregationFilter):
                yield value
            elif isinstance(value, Filter):
                yield from QueryTranspiler._iter_aggregation_filters(value)
        for value in query_filter.or_:
            yield from QueryTranspiler._iter_aggregation_filters(value)
        if query_filter.not_ is not None:
            yield from QueryTranspiler._iter_aggregation_filters(query_filter.not_)

    def _build_aggregation_joins(self, specs: dict[QueryNodeType, AggregationSpec]) -> None:
        """Builds each spec's join exactly once and records object column references.

        For every spec a single lateral or CTE join is built holding all of its
        function columns. Each function column is then exposed on
        ``collector.columns`` as an object reference off the built selectable, so the
        consume sites only need to look columns up by their function node.

        Args:
            specs: The aggregation specs to materialize, keyed by aggregation node.
        """
        for aggregation_node, spec in specs.items():
            if not spec.functions:
                continue
            if self._inspector.db_features.supports_lateral:
                join = self._aggregation_lateral_join(aggregation_node, spec.functions.values(), spec.alias)
            else:
                join = self._aggregation_cte_join(
                    node=aggregation_node,
                    alias=spec.alias,
                    statement=select(*spec.functions.values()),
                )
            for function_node in spec.functions:
                self.scope.collector.columns[function_node] = self.scope.scoped_column(
                    join.selectable, self.scope.key(function_node)
                )
            self._aggregation_joins[aggregation_node] = join

    def _emit_aggregation_join(self, aggregation_node: QueryNodeType) -> Join | None:
        """Returns the built join for an aggregation node once, then ``None`` thereafter.

        Guards against the join being added to ``query.joins`` more than once across the
        two-phase order-by recompute.

        Args:
            aggregation_node: The aggregation node whose join should be emitted.

        Returns:
            The aggregation join the first time it is requested, ``None`` afterwards.
        """
        join = self._aggregation_joins.get(aggregation_node)
        if join is None or aggregation_node in self._emitted_aggregation_joins:
            return None
        self._emitted_aggregation_joins.add(aggregation_node)
        return join

    def _aggregation_filter(self, aggregation: AggregationFilter) -> tuple[Join | None, list[ColumnElement[bool]]]:
        """Looks up an aggregation filter's column and builds its filter expressions.

        The join and its columns are built once by :meth:`_build_aggregation_joins`;
        this method only reads the resolved column and emits the join (at most once).

        Args:
            aggregation: The aggregation filter to process.

        Returns:
            A tuple containing:
                - The join object the first time it is needed, ``None`` otherwise.
                - A list of boolean expressions for the filter.
        """
        aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
        spec = self._aggregation_specs_by_node[aggregation_node]
        function_node, _ = self.scope.inspect(aggregation.field_node).filter_function(
            spec.alias, distinct=aggregation.distinct
        )
        function_column = self.scope.collector.columns[function_node]
        self.scope.collector.where.add(function_node)
        bool_expressions = aggregation.predicate.to_expressions(self.dialect, function_column)
        return self._emit_aggregation_join(aggregation_node), bool_expressions

    def _upsert_aggregations(self, aggregation_node: QueryNodeType) -> tuple[list[NamedColumn[Any]], Join | None]:
        """Looks up the columns of an already-built aggregation join.

        The join and its columns are built once by :meth:`_build_aggregation_joins`;
        this method only reads the resolved columns and emits the join (at most once).

        Args:
            aggregation_node: The aggregation node whose columns are requested.

        Returns:
            A tuple of the resolved function columns and the join (emitted at most once).
        """
        spec = self._aggregation_specs_by_node[aggregation_node]
        function_columns = [self.scope.collector.columns[function_node] for function_node in spec.functions]
        return function_columns, self._emit_aggregation_join(aggregation_node)

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
        target_alias: AliasedClass[Any] = cast("AliasedClass[Any]", aliased(target_mapper, flat=True))
        order_by = relation_filter.order_by if isinstance(relation_filter, OrderByRelationFilterDTO) else []
        with self._sub_scope(target_mapper.class_, target_alias):
            query_graph = QueryGraph(self.scope, order_by=order_by)  # ty:ignore[invalid-argument-type]
            query = self._build_query(query_graph, limit=relation_filter.limit, offset=relation_filter.offset)
        join = self._join_strategy.relation_join(self.scope, node, target_alias, query, is_outer)
        join.order_nodes = query_graph.order_by_nodes
        return join

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
        root_relation = self.scope.aliased_attribute(node).of_type(inspect(alias))
        lateral_statement = select(*function_columns).where(root_relation).lateral()
        return AggregationJoin(target=lateral_statement, onclause=true(), node=node)

    def _aggregation_cte_join(
        self, node: QueryNodeType, alias: AliasedClass[Any], statement: Select[Any]
    ) -> AggregationJoin:
        """Creates an aggregation join using a Common Table Expression (CTE).

        This method is used for aggregations when LATERAL joins are not supported
        or not suitable.

        Args:
            node: The query node to create an aggregation join for.
            alias: The aliased class for the target of the aggregation.
            statement: The SQLAlchemy select statement for the aggregation.

        Returns:
            An AggregationJoin object representing the CTE-based aggregation join.
        """
        remote_fks = self.scope.inspect(node).foreign_key_columns("target", alias)
        cte_statement = (
            statement.add_columns(*remote_fks)
            .group_by(*remote_fks)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
            .cte()
        )
        cte_alias = aliased(alias, cte_statement)
        return AggregationJoin(
            target=cte_alias,
            onclause=self.scope.aliased_attribute(node).of_type(cte_alias),
            node=node,
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

    def _default_order_columns(self) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
        """Builds ORDER BY columns from the field's ``default_order_by`` expressions.

        Each expression's column is adapted to the active root alias so the ordering
        is correct inside pagination/distinct subqueries.

        Returns:
            A list of ``(aliased_column, OrderByEnum)`` tuples in declared order.

        Raises:
            StrawchemyFieldError: If an expression references a column that is not a
                column of the root model.
        """
        alias_insp = inspect(self.scope.root_alias)
        column_keys = {attr.key for attr in alias_insp.mapper.column_attrs}
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        for expr in self._default_order_by:
            decomposed = decompose_order_by(expr)
            if (
                decomposed.key not in column_keys
            ):  # pragma: no cover  # defensive: shadowed by StrawchemyField's stricter schema-build validation
                msg = f"`default_order_by` column '{decomposed.key}' is not a column of {self.scope.model.__name__}"
                raise StrawchemyFieldError(msg)
            aliased_attribute = alias_insp.mapper.attrs[decomposed.key].class_attribute.adapt_to_entity(alias_insp)
            columns.append((aliased_attribute, decomposed.order))
        return columns

    def _order_by(self, order_by_nodes: list[QueryNodeType]) -> OrderBy:
        """Creates ORDER BY expressions and joins from a list of nodes.

        Args:
            order_by_nodes: The nodes to create order by expressions from.

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
                self.scope.collector.order_by.add(node)
            if node.metadata.data.order_by is None:
                msg = "Missing order by value"
                raise TranspilingError(msg)
            if node.value.is_function_arg or node.value.is_function:
                first_aggregate_parent = node.find_parent(lambda node: node.value.is_aggregate, strict=True)
                function_columns, new_join = self._upsert_aggregations(first_aggregate_parent)
                columns.extend([(function_column, node.metadata.data.order_by) for function_column in function_columns])
                seen_aggregation_nodes.add(first_aggregate_parent)
                if new_join:
                    joins.append(new_join)
            else:
                columns.append((self.scope.aliased_attribute(node), node.metadata.data.order_by))
        no_user_columns = not columns
        # PK tiebreaker is appended after any default_order_by columns; no_user_columns
        # (captured before the default block) prevents doubling up when the client ordered.
        if no_user_columns and self._default_order_by:
            columns.extend(self._default_order_columns())
        if no_user_columns and self._deterministic_ordering:
            pk_aliases = [
                pk_attribute.adapt_to_entity(inspect(self.scope.root_alias))
                for pk_attribute in self._inspector.pk_attributes(self.scope.model.__mapper__)
            ]
            columns.extend([(id_col, OrderByEnum.ASC) for id_col in pk_aliases])
        return OrderBy(self._inspector.db_features, columns, joins)

    def _select(self, selection_tree: QueryNodeType) -> tuple[Select[tuple[DeclarativeT]], list[Join]]:
        """Builds the main SELECT statement based on the selection tree.

        This method constructs the core SQLAlchemy SELECT statement, incorporating
        selected columns, aggregations, and eager loading options for relations
        defined in the `selection_tree`.

        Args:
            selection_tree: The query node tree representing the fields to select.

        Returns:
            A tuple containing:
                - The constructed SQLAlchemy Select statement.
                - A list of Join objects required for aggregations.
        """
        aggregation_joins: list[Join] = []
        statement = self._base_statement()
        root_columns, column_transforms = self.scope.inspect(selection_tree).columns()
        for column_transform in column_transforms:
            statement = statement.add_columns(column_transform.attribute)
        for node in selection_tree.iter_depth_first():
            if node.value.is_aggregate:
                function_columns, new_join = self._upsert_aggregations(node)
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
        """Determines if DISTINCT ON should be implemented using RANK() window function.

        This is necessary when the database dialect does not natively support
        DISTINCT ON, or when specific ordering is required with DISTINCT ON.

        Args:
            query_graph: The query graph containing distinct_on and order_by information.

        Returns:
            True if RANK() should be used for distinct operation, False otherwise.
        """
        if self._inspector.db_features.supports_distinct_on:
            return bool(
                query_graph.distinct_on
                and (query_graph.order_by_tree or self._deterministic_ordering or self._default_order_by)
            )
        return bool(query_graph.distinct_on)

    def _relation_order_by(self, query_graph: QueryGraph[DeclarativeT], query: Query) -> list[OrderBySpec]:
        """Generates ORDER BY specifications for related entities in the query.

        Ensures consistent ordering for joined relations, especially when
        deterministic ordering is enabled or specific order nodes are defined for a join.

        Args:
            query_graph: The query graph containing selection and ordering information.
            query: The current Query object being built.

        Returns:
            A list of OrderBySpec tuples for related entities.
        """
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
                        (
                            self.scope.scoped_column(join.selectable, node.value.model_field_name),
                            node.metadata.data.order_by,
                        )
                        for node in join.order_nodes
                        if node.metadata.data.order_by
                    ]
                )
        return order_by_spec

    def _filter_pass(
        self, query_graph: QueryGraph[DeclarativeT], query: Query, allow_null: bool
    ) -> tuple[list[Join], set[QueryNodeType]]:
        """Populates ``query.where`` from the graph filter.

        Args:
            query_graph: The graph representation of the query to build.
            query: The query object whose WHERE clause is populated in place.
            allow_null: Whether to allow nulls in filter conditions.

        Returns:
            A tuple containing:
                - List of joins required by the filter.
                - The set of nodes those joins were built from.
        """
        joins: list[Join] = []
        subquery_join_nodes: set[QueryNodeType] = set()
        if query_graph.query_filter:
            query.where = self._where(query_graph.query_filter, allow_null)
            joins.extend(query.where.joins)
            subquery_join_nodes = {join.node for join in query.where.joins}
        return joins, subquery_join_nodes

    def _order_pass(self, query_graph: QueryGraph[DeclarativeT]) -> OrderBy | None:
        """Builds the initial ORDER BY when any ordering applies.

        Args:
            query_graph: The graph representation of the query to build.

        Returns:
            The constructed OrderBy, including default and deterministic columns, or None
            when no client, default or deterministic ordering applies.
        """
        if not (query_graph.order_by_tree or self._deterministic_ordering or self._default_order_by):
            return None
        return self._order_by(query_graph.order_by_nodes)

    def _subquery_pass(
        self,
        query_graph: QueryGraph[DeclarativeT],
        query: Query,
        subquery_builder: SubqueryBuilder[DeclarativeT],
        joins: list[Join],
        distinct_on_rank: bool,
    ) -> None:
        """Builds the pagination/distinct subquery and re-roots the scope onto it.

        Recomputes joins and ORDER BY against the new root alias, mutating ``query`` in
        place. The ORDER BY recompute is unconditional, matching the original behavior (it
        yields an empty OrderBy when no ordering applies, so relation ORDER BY columns are
        still appended for paginated subqueries).

        Args:
            query_graph: The graph representation of the query to build.
            query: The query object re-rooted and updated in place.
            subquery_builder: The builder used to construct the subquery.
            joins: The joins gathered so far, passed through to the subquery.
            distinct_on_rank: Whether the subquery applies DISTINCT ON via a window rank.
        """
        subquery_alias = subquery_builder.build(query_graph, dataclasses.replace(query, joins=joins))
        self.scope.replace(alias=subquery_alias)
        query.offset = None
        query.joins = self._gather_joins(query_graph.root_join_tree, is_outer=True)
        query.order_by = self._order_by(query_graph.order_by_nodes)
        query.joins.extend(query.order_by.joins)
        if distinct_on_rank:
            query.where = Where.from_expressions(subquery_builder.distinct_on_condition(subquery_alias))
        elif query.where:
            query.where.clear_expressions()

    def _build_query(
        self,
        query_graph: QueryGraph[DeclarativeT],
        limit: int | None = None,
        offset: int | None = None,
        allow_null: bool = False,
    ) -> Query:
        """Constructs the final SQLAlchemy Query object from a QueryGraph.

        This method orchestrates the assembly of the SELECT statement, WHERE clauses,
        ORDER BY clauses, LIMIT/OFFSET, DISTINCT ON logic, and all necessary JOINs
        (including subquery and aggregation joins).

        Args:
            query_graph: The graph representation of the query to build.
            limit: Optional limit for pagination.
            offset: Optional offset for pagination.
            allow_null: Whether to allow nulls in filter conditions.

        Returns:
            The fully constructed Query object.
        """
        distinct_on_rank = self._use_distinct_rank(query_graph)
        query = Query(
            self._inspector.db_features,
            limit=limit,
            offset=offset,
            distinct_on=DistinctOn(query_graph),
            use_distinct_on=not distinct_on_rank,
        )
        subquery_needed = self.scope.is_root and (limit is not None or offset is not None or distinct_on_rank)
        subquery_builder = SubqueryBuilder(
            self.scope,
            self._hook_applier,
            self._inspector.db_features,
            filter_statement_join=(
                self._apply_filter_statement if self.scope.is_root and self._statement is not None else None
            ),
        )

        if subquery_needed:
            self.scope.replace(alias=subquery_builder.alias)
            if self._statement is not None:
                self._filter_in_subquery = True

        # Build every aggregation join once with all of its function columns, before the
        # filter/order/select passes consume them as object references.
        self._emitted_aggregation_joins = set()
        self._aggregation_specs_by_node = self._aggregation_specs(query_graph)
        self._build_aggregation_joins(self._aggregation_specs_by_node)

        joins, subquery_join_nodes = self._filter_pass(query_graph, query, allow_null)

        order_by = self._order_pass(query_graph)
        if order_by is not None:
            query.order_by = order_by
            joins.extend(order_by.joins)

        if query_graph.subquery_join_tree:
            joins.extend(
                join
                for join in self._gather_joins(query_graph.subquery_join_tree, is_outer=True)
                if join.node not in subquery_join_nodes
            )

        if subquery_needed:
            self._subquery_pass(query_graph, query, subquery_builder, joins, distinct_on_rank)
        else:
            query.joins = joins + [
                join
                for join in self._gather_joins(query_graph.root_join_tree, is_outer=True)
                if join.node not in subquery_join_nodes
            ]

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
