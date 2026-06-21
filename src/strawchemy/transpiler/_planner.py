"""Builds a QueryPlan from a QueryGraph through composable planning passes.

Each pass — AggregationPlan, FilterPlan, OrderPlan, ProjectionPlan — exposes a ``plan()``
classmethod returning an immutable result; ``plan_query`` composes them into a ``QueryPlan``.
SQLAlchemy statements are assembled only by ``QueryPlan.emit``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy import and_, func, inspect, not_, null, or_, select, true
from sqlalchemy.orm import Mapper, RelationshipProperty, aliased, class_mapper, contains_eager, load_only, raiseload

from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.dto.strawberry import (
    AggregationFilter,
    Filter,
    OrderByEnum,
    OrderByRelationFilterDTO,
    QueryNode,
    decompose_order_by,
)
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.repository.typing import DeclarativeT
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._plan import FilterSemiJoin, HookSpec, QueryPlan
from strawchemy.transpiler._query import (
    AggregationJoin,
    AggregationSpec,
    Conjunction,
    DistinctOn,
    HookApplier,
    Join,
    OrderBy,
    QueryGraph,
    Where,
)
from strawchemy.transpiler._scope import AliasContext, require_corresponding_column
from strawchemy.transpiler._strategies import select_join_strategy

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import Dialect, Label, Select
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql.elements import KeyedColumnElement, UnaryExpression
    from sqlalchemy.sql.selectable import Alias

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._strategies import JoinStrategy
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import OrderByExpr, QueryNodeType, SupportedDialect

__all__ = ("AggregationPlan", "FilterPlan", "OrderPlan", "PlanContext", "ProjectionPlan", "plan_query")


@dataclass(frozen=True)
class PlanContext(Generic[DeclarativeT]):
    """The shared planning environment threaded through a single query plan.

    Carries the long-lived deps that every planning pass needs.  Built once per
    top-level plan and re-derived for each related-collection sub-plan via
    ``replace`` (see ``build_join``).
    """

    aliases: AliasContext[DeclarativeT]
    """The query scope; re-rooted in place by the subquery path."""
    db_features: DatabaseFeatures
    """Database-capability flags (cannot be derived from ``aliases``)."""
    dialect: Dialect
    """The SQLAlchemy dialect used for expression building."""
    hook_applier: HookApplier
    """Applies query hooks and collects load options."""
    join_strategy: JoinStrategy
    """Builds relation joins (lateral or CTE), chosen from ``db_features``."""
    default_order_by: tuple[OrderByExpr, ...] = ()
    """Default ordering applied when the client supplies none."""
    deterministic_ordering: bool = False
    """Whether to append PK tiebreaker columns to ORDER BY."""
    statement: Select[Any] | None = None
    """Optional base filter Select joined in as a PK semi-join."""

    @classmethod
    def create(
        cls,
        model: type[DeclarativeT],
        dialect: Dialect,
        *,
        statement: Select[tuple[DeclarativeT]] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> PlanContext[DeclarativeT]:
        """Builds a root planning environment for a model.

        Args:
            model: The SQLAlchemy model to plan queries for.
            dialect: The SQLAlchemy dialect to use.
            statement: An optional base filter Select to build upon.
            query_hooks: Optional hooks to apply during planning.
            deterministic_ordering: Whether to ensure deterministic ordering.
            default_order_by: Default ordering applied when the client supplies none.

        Returns:
            A root ``PlanContext`` whose ``aliases`` scope is freshly rooted on ``model``.
        """
        supported_dialect = cast("SupportedDialect", dialect.name)
        inspector = SQLAlchemyGraphQLInspector(supported_dialect, [model.registry])
        db_features = inspector.db_features
        ctx = AliasContext(model, supported_dialect, inspector=inspector)
        return cls(
            aliases=ctx,
            db_features=db_features,
            dialect=dialect,
            hook_applier=HookApplier(ctx, query_hooks or defaultdict(list)),
            join_strategy=select_join_strategy(db_features),
            default_order_by=tuple(default_order_by or ()),
            deterministic_ordering=deterministic_ordering,
            statement=statement,
        )

    def build_join(self, node: QueryNodeType, is_outer: bool = False) -> Join:
        """Creates a relation join for a query node.

        For a node without a relation filter this is a plain ``Join`` on the
        aliased attribute.  Otherwise a fresh sub-scope is derived
        (``replace(self, aliases=self.aliases.sub(...), statement=None)``), its nested
        plan is built via ``plan_query``, and the configured join strategy turns
        that plan into the relation join.

        Args:
            node: The query node to create a join for.
            is_outer: Whether to create an outer join.

        Returns:
            A ``Join`` for the node, attached to the parent scope (``self.aliases``).
        """
        aliased_attribute = self.aliases.aliased_attribute(node)
        relation_filter = node.metadata.data.relation_filter

        if not relation_filter:
            return Join(aliased_attribute, node=node, is_outer=is_outer)

        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        target_mapper: Mapper[Any] = relationship.mapper.mapper
        target_alias: AliasedClass[Any] = cast("AliasedClass[Any]", aliased(target_mapper, flat=True))
        order_by = relation_filter.order_by if isinstance(relation_filter, OrderByRelationFilterDTO) else []

        sub_context = replace(self, aliases=self.aliases.sub(target_mapper.class_, target_alias), statement=None)
        query_graph = QueryGraph(sub_context.aliases, order_by=order_by)  # ty:ignore[invalid-argument-type]
        plan = plan_query(query_graph, sub_context, limit=relation_filter.limit, offset=relation_filter.offset)
        join = self.join_strategy.relation_join(self.aliases, node, target_alias, plan, is_outer)
        join.order_nodes = query_graph.order_by_nodes
        return join


@dataclass(frozen=True)
class AggregationPlan:
    """Aggregation joins and their function-column references, built once and threaded into passes."""

    columns: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Function node -> its built aggregation column (corresponded onto the join selectable)."""
    joins: tuple[AggregationJoin, ...] = ()
    """The aggregation lateral/CTE joins, built once."""
    aliases: Mapping[QueryNodeType, AliasedClass[Any]] = field(default_factory=dict)
    """Aggregation node -> its adaptation alias (spec.alias), needed by filter_function."""
    node_functions: Mapping[QueryNodeType, tuple[QueryNodeType, ...]] = field(default_factory=dict)
    """Aggregation node -> ordered tuple of its function-node keys, in ``spec.functions`` key order."""

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any]) -> AggregationPlan:
        """Builds aggregation joins and function-column references without mutating scope.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``db_features`` read here).

        Returns:
            An ``AggregationPlan`` with columns, joins, aliases, and node_functions.
        """
        specs = cls._accumulate_specs(query_graph, context)
        columns: dict[QueryNodeType, ColumnElement[Any]] = {}
        aliases: dict[QueryNodeType, AliasedClass[Any]] = {}
        node_functions: dict[QueryNodeType, tuple[QueryNodeType, ...]] = {}
        joins: list[AggregationJoin] = []

        for aggregation_node, spec in specs.items():
            if not spec.functions:
                continue
            if context.db_features.supports_lateral:
                join = cls._lateral_join(aggregation_node, spec.functions.values(), spec.alias, context)
            else:
                join = cls._cte_join(
                    node=aggregation_node, alias=spec.alias, statement=select(*spec.functions.values()), context=context
                )
            for function_node, inner_label in spec.functions.items():
                columns[function_node] = require_corresponding_column(join.selectable, inner_label)
            aliases[aggregation_node] = spec.alias
            node_functions[aggregation_node] = tuple(spec.functions.keys())
            joins.append(join)

        return cls(columns=columns, joins=tuple(joins), aliases=aliases, node_functions=node_functions)

    @staticmethod
    def _accumulate_specs(
        query_graph: QueryGraph[Any], context: PlanContext[Any]
    ) -> dict[QueryNodeType, AggregationSpec]:
        """Accumulates one AggregationSpec per aggregation node from the query graph.

        Visits sources in fixed order — filter, order-by, selection — and deduplicates
        function expressions per aggregation node by their function_node key.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases`` used for inspection/alias creation).

        Returns:
            An ordered mapping of aggregation node to its accumulated spec.
        """
        aliases = context.aliases
        specs: dict[QueryNodeType, AggregationSpec] = {}

        # Filter source
        if query_graph.query_filter is not None:
            for aggregation in query_graph.query_filter.iter_aggregation_filters():
                aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
                spec = specs.get(aggregation_node)
                if spec is None:
                    spec = specs[aggregation_node] = AggregationSpec.create(aggregation_node, aliases)
                function_node, function = aliases.inspect(aggregation.field_node).filter_function(
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
            spec = specs.get(aggregation_node)
            if spec is None:
                spec = specs[aggregation_node] = AggregationSpec.create(aggregation_node, aliases)
            for child_inspect in aliases.inspect(aggregation_node).children:
                for function_node, function in child_inspect.output_functions(spec.alias).items():
                    if function_node not in spec.functions:
                        spec.functions[function_node] = function

        return specs

    @staticmethod
    def _lateral_join(
        node: QueryNodeType, function_columns: Iterable[ColumnElement[Any]], alias: Any, context: PlanContext[Any]
    ) -> AggregationJoin:
        """Creates a lateral aggregation join for a query node.

        Args:
            node: The aggregation node.
            function_columns: The aggregate function columns to include in the lateral.
            alias: The aliased target class the function expressions are adapted to.
            context: The shared planning context (``aliases`` provides inspect/aliased_attribute).

        Returns:
            An AggregationJoin backed by a lateral subquery.
        """
        root_relation = context.aliases.aliased_attribute(node).of_type(inspect(alias))
        lateral_statement = select(*function_columns).where(root_relation).lateral()
        return AggregationJoin(target=lateral_statement, onclause=true(), node=node)

    @staticmethod
    def _cte_join(node: QueryNodeType, alias: Any, statement: Any, context: PlanContext[Any]) -> AggregationJoin:
        """Creates a CTE-based aggregation join for a query node.

        Args:
            node: The aggregation node.
            alias: The aliased target class for the aggregation target.
            statement: The SQLAlchemy select statement selecting the aggregate functions.
            context: The shared planning context (``aliases`` provides inspect for FK resolution).

        Returns:
            An AggregationJoin backed by a CTE.
        """
        aliases = context.aliases
        remote_fks = aliases.inspect(node).foreign_key_columns("target", alias)
        cte_statement = (
            statement.add_columns(*remote_fks)
            .group_by(*remote_fks)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
            .cte()
        )
        cte_alias = aliased(alias, cte_statement)
        return AggregationJoin(target=cte_alias, onclause=aliases.aliased_attribute(node).of_type(cte_alias), node=node)

    def columns_for(self, node: QueryNodeType) -> list[ColumnElement[Any]]:
        """Returns the function columns for an aggregation node in spec order.

        Args:
            node: The aggregation node whose function columns are requested.

        Returns:
            A list of labelled function columns in ``node_functions`` key order, or empty.
        """
        fn_keys = self.node_functions.get(node)
        if fn_keys is None:
            return []
        return [self.columns[fn] for fn in fn_keys]

    def join_for(self, node: QueryNodeType) -> AggregationJoin | None:
        """Returns the AggregationJoin for an aggregation node, or None if absent.

        Args:
            node: The aggregation node to look up.

        Returns:
            The matching AggregationJoin, or None.
        """
        for candidate in self.joins:
            if candidate.node is node:
                return candidate
        return None

    def upsert(self, node: QueryNodeType, emitted: set[QueryNodeType]) -> tuple[list[ColumnElement[Any]], Join | None]:
        """Returns the node's function columns, returning its join at most once.

        Args:
            node: The aggregation node whose columns are requested.
            emitted: Mutable set tracking already-returned aggregation joins.

        Returns:
            The resolved function columns and the join (returned at most once per node).
        """
        function_columns = self.columns_for(node)
        new_join: Join | None = None
        if node not in emitted:
            emitted.add(node)
            new_join = self.join_for(node)
        return function_columns, new_join


@dataclass(frozen=True)
class FilterPlan:
    """WHERE predicates and the relation joins they require."""

    where: tuple[ColumnElement[bool], ...] = ()
    joins: tuple[Join, ...] = ()
    referenced_functions: frozenset[QueryNodeType] = frozenset()
    """Function nodes referenced in WHERE predicates (for subquery hoist)."""

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        allow_null: bool = False,
    ) -> FilterPlan:
        """Builds the WHERE predicates and their relation joins.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            allow_null: Whether to allow null values in filter conditions.

        Returns:
            A FilterPlan with WHERE predicates, joins, and referenced functions.
        """
        if not query_graph.query_filter:
            return cls()

        emitted_agg_joins: set[QueryNodeType] = set()
        where_function_nodes: set[QueryNodeType] = set()

        where = cls._where(
            query_graph.query_filter, context, agg_plan, emitted_agg_joins, where_function_nodes, allow_null
        )
        return cls(
            where=tuple(where.expressions),
            joins=tuple(where.joins),
            referenced_functions=frozenset(where_function_nodes),
        )

    @staticmethod
    def _to_expressions(
        context: PlanContext[Any],
        dto_filter: GraphQLComparison,
        override: ColumnElement[Any] | None = None,
        not_null_check: bool = False,
    ) -> list[ColumnElement[bool]]:
        """Converts a DTO filter comparison to a list of SQLAlchemy expressions.

        Args:
            context: The shared planning context (``aliases``, ``dialect`` read here).
            dto_filter: The DTO filter comparison to convert.
            override: An optional column element to override the filter attribute.
            not_null_check: Whether to add a not-null check to the expressions.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        attribute = override if override is not None else context.aliases.aliased_attribute(dto_filter.field_node)
        expressions: list[ColumnElement[bool]] = dto_filter.to_expressions(context.dialect, attribute)
        if not_null_check:
            expressions.append(attribute.is_not(null()))
        return expressions

    @staticmethod
    def _aggregation_filter(
        aggregation: AggregationFilter,
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
    ) -> tuple[Join | None, list[ColumnElement[bool]], QueryNodeType]:
        """Looks up an aggregation filter's column and builds its filter expressions.

        Args:
            aggregation: The aggregation filter to process.
            context: The shared planning context (``aliases``, ``dialect`` read here).
            agg_plan: The pre-built aggregation plan providing columns and aliases.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.

        Returns:
            A tuple of:
                - The aggregation join the first time it is needed for this node, ``None`` otherwise.
                - A list of boolean filter expressions.
                - The function_node referenced in this WHERE predicate.
        """
        aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
        alias = agg_plan.aliases[aggregation_node]
        function_node, _ = context.aliases.inspect(aggregation.field_node).filter_function(
            alias, distinct=aggregation.distinct
        )
        function_column = agg_plan.columns[function_node]
        bool_expressions = aggregation.predicate.to_expressions(context.dialect, function_column)

        # Emit the aggregation join at most once.
        agg_join: Join | None = None
        if aggregation_node not in emitted_agg_joins:
            emitted_agg_joins.add(aggregation_node)
            agg_join = agg_plan.join_for(aggregation_node)

        return agg_join, bool_expressions, function_node

    @staticmethod
    def _gather_conjunctions(
        query: Sequence[Filter | AggregationFilter | GraphQLComparison],
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        where_function_nodes: set[QueryNodeType],
        not_null_check: bool = False,
    ) -> Conjunction:
        """Gathers all conjunctions from a sequence of filters.

        Args:
            query: A sequence of filters to gather conjunctions from.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            where_function_nodes: Mutable set accumulating function nodes in WHERE.
            not_null_check: Whether to add not-null checks.

        Returns:
            A conjunction of expressions, joins, and common join path.
        """
        bool_expressions: list[ColumnElement[bool]] = []
        joins: list[Join] = []
        common_join_path: list[QueryNodeType] = []
        node_path: list[QueryNodeType] = []

        for value in query:
            if isinstance(value, AggregationFilter):
                node_path = value.field_node.path_from_root()
                agg_join, aggregation_expressions, function_node = FilterPlan._aggregation_filter(
                    value, context, agg_plan, emitted_agg_joins
                )
                where_function_nodes.add(function_node)
                if agg_join is not None:
                    joins.append(agg_join)
                bool_expressions.extend(aggregation_expressions)
            elif isinstance(value, GraphQLComparison):
                node_path = value.field_node.path_from_root()
                bool_expressions.extend(FilterPlan._to_expressions(context, value, not_null_check=not_null_check))
            else:
                conjunction = FilterPlan._conjunctions(
                    value, context, agg_plan, emitted_agg_joins, where_function_nodes, not_null_check
                )
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

    @staticmethod
    def _conjunctions(
        query: Filter,
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        where_function_nodes: set[QueryNodeType],
        allow_null: bool = False,
    ) -> Conjunction:
        """Processes a filter's AND, OR, and NOT conditions into a conjunction.

        Args:
            query: The filter to process.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            where_function_nodes: Mutable set accumulating function nodes in WHERE.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A conjunction of expressions, joins, and common join path.
        """
        bool_expressions: list[ColumnElement[bool]] = []
        and_conjunction = FilterPlan._gather_conjunctions(
            query.and_, context, agg_plan, emitted_agg_joins, where_function_nodes, allow_null
        )
        or_conjunction = FilterPlan._gather_conjunctions(
            query.or_, context, agg_plan, emitted_agg_joins, where_function_nodes, allow_null
        )
        common_path = QueryNode.common_path(and_conjunction.common_join_path, or_conjunction.common_join_path)
        joins = [*and_conjunction.joins, *or_conjunction.joins]

        if query.not_:
            not_conjunction = FilterPlan._gather_conjunctions(
                [query.not_],
                context,
                agg_plan,
                emitted_agg_joins,
                where_function_nodes,
                not_null_check=True,
            )
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

    @staticmethod
    def _where(
        query_filter: Filter,
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        where_function_nodes: set[QueryNodeType],
        allow_null: bool = False,
    ) -> Where:
        """Creates WHERE expressions and joins from a filter.

        Args:
            query_filter: The filter to create expressions from.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            where_function_nodes: Mutable set accumulating function nodes in WHERE.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A Where containing expressions and required joins.
        """
        conjunction = FilterPlan._conjunctions(
            query_filter, context, agg_plan, emitted_agg_joins, where_function_nodes, allow_null
        )
        return Where(
            conjunction,
            [
                *conjunction.joins,
                *[
                    context.build_join(node, False)
                    for node in conjunction.common_join_path
                    if not node.is_root and node.value.is_relation
                ],
            ],
        )


@dataclass(frozen=True)
class OrderPlan:
    """Built ORDER BY expressions and the relation joins they require."""

    expressions: tuple[UnaryExpression[Any], ...] = ()
    joins: tuple[Join, ...] = ()
    referenced_functions: frozenset[QueryNodeType] = frozenset()
    """Function nodes referenced in ORDER BY (for subquery hoist)."""

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        existing_joins: Sequence[Join],
    ) -> OrderPlan:
        """Builds the ORDER BY expressions and their relation joins.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``db_features``,
                ``default_order_by``, ``deterministic_ordering`` read here).
            agg_plan: The pre-built aggregation plan providing function columns.
            existing_joins: The relation joins gathered so far.

        Returns:
            An OrderPlan with expressions, new relation joins, and referenced functions.
        """
        _default_order_by = list(context.default_order_by)

        if not (query_graph.order_by_tree or context.deterministic_ordering or _default_order_by):
            return cls()

        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        joins: list[Join] = []
        order_by_function_nodes: set[QueryNodeType] = set()
        seen_aggregation_nodes: set[QueryNodeType] = set()
        emitted_agg_joins: set[QueryNodeType] = set()

        for node in query_graph.order_by_nodes:
            cls._build_node(
                node,
                context,
                agg_plan,
                seen_aggregation_nodes,
                emitted_agg_joins,
                order_by_function_nodes,
                columns,
                joins,
            )

        no_user_columns = not columns
        if no_user_columns and _default_order_by:
            columns.extend(cls._default_order_columns(context))
        if no_user_columns and context.deterministic_ordering:
            pk_aliases = [
                pk_attribute.adapt_to_entity(inspect(context.aliases.root_alias))
                for pk_attribute in SQLAlchemyInspector.pk_attributes(context.aliases.model.__mapper__)
            ]
            columns.extend([(id_col, OrderByEnum.ASC) for id_col in pk_aliases])

        order_by = OrderBy(context.db_features, columns, joins)

        relation_order_columns = cls._relation_order_by(query_graph, context, existing_joins)
        order_by.columns.extend(relation_order_columns)

        return cls(
            expressions=tuple(order_by.expressions),
            joins=tuple(order_by.joins),
            referenced_functions=frozenset(order_by_function_nodes),
        )

    @staticmethod
    def _default_order_columns(
        context: PlanContext[Any],
    ) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
        """Builds ORDER BY columns from the context's default_order_by expressions.

        Args:
            context: The shared planning context (``aliases`` root alias, ``default_order_by``).

        Returns:
            A list of ``(aliased_column, OrderByEnum)`` tuples in declared order.

        Raises:
            StrawchemyFieldError: If an expression references a column not on the root model.
        """
        ctx = context.aliases
        alias_insp = inspect(ctx.root_alias)
        column_keys = {attr.key for attr in alias_insp.mapper.column_attrs}
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        for expr in context.default_order_by:
            decomposed = decompose_order_by(expr)
            if decomposed.key not in column_keys:  # pragma: no cover  # defensive
                msg = f"`default_order_by` column '{decomposed.key}' is not a column of {ctx.model.__name__}"
                raise StrawchemyFieldError(msg)
            aliased_attribute = alias_insp.mapper.attrs[decomposed.key].class_attribute.adapt_to_entity(alias_insp)
            columns.append((aliased_attribute, decomposed.order))
        return columns

    @staticmethod
    def _build_node(
        node: QueryNodeType,
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        seen_aggregation_nodes: set[QueryNodeType],
        emitted_agg_joins: set[QueryNodeType],
        order_by_function_nodes: set[QueryNodeType],
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]],
        joins: list[Join],
    ) -> None:
        """Processes a single order-by node, updating columns/joins/tracked sets in place.

        Extracted from ``plan`` to reduce cyclomatic complexity.

        Args:
            node: The order-by node to process.
            context: The shared planning context (``aliases`` read here).
            agg_plan: The pre-built aggregation plan.
            seen_aggregation_nodes: Mutable set of already-seen aggregation parents.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            order_by_function_nodes: Mutable set accumulating function nodes in ORDER BY.
            columns: Mutable list accumulating ``(column, order)`` pairs.
            joins: Mutable list accumulating new relation/aggregation joins.
        """
        if (
            node.value.is_function_arg
            and node.find_parent(lambda n: n.value.is_aggregate, strict=True) in seen_aggregation_nodes
        ):
            return
        if node.value.is_function:
            order_by_function_nodes.add(node)
        if node.metadata.data.order_by is None:
            msg = "Missing order by value"
            raise TranspilingError(msg)
        if node.value.is_function_arg or node.value.is_function:
            first_aggregate_parent = node.find_parent(lambda n: n.value.is_aggregate, strict=True)
            agg_join: Join | None = None
            if first_aggregate_parent not in emitted_agg_joins:
                emitted_agg_joins.add(first_aggregate_parent)
                agg_join = agg_plan.join_for(first_aggregate_parent)
            agg_columns = agg_plan.columns_for(first_aggregate_parent)
            columns.extend([(col, node.metadata.data.order_by) for col in agg_columns])
            seen_aggregation_nodes.add(first_aggregate_parent)
            if agg_join is not None:
                joins.append(agg_join)
        else:
            columns.append((context.aliases.aliased_attribute(node), node.metadata.data.order_by))

    @staticmethod
    def _relation_order_by(
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        joins: Sequence[Join],
    ) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
        """Generates ORDER BY specs for related entities.

        Args:
            query_graph: The query graph containing selection and ordering information.
            context: The shared planning context (``aliases``, ``deterministic_ordering`` read here).
            joins: The relation joins gathered so far.

        Returns:
            A list of ``(column, OrderByEnum)`` tuples for relation ordering.
        """
        ctx = context.aliases
        deterministic_ordering = context.deterministic_ordering
        selected_tree = query_graph.resolved_selection_tree()
        order_by_spec: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        for join in sorted(joins):
            if (
                isinstance(join, AggregationJoin)
                or join.node in query_graph.order_by_nodes
                or not selected_tree.find_child(
                    lambda node, _join=join: node.value.model_field is _join.node.value.model_field
                )
            ):
                continue
            if not join.order_nodes and deterministic_ordering:
                order_by_spec.extend(
                    [(attribute, OrderByEnum.ASC) for attribute in ctx.aliased_id_attributes(join.node)]
                )
            elif join.order_nodes:
                order_by_spec.extend(
                    [
                        (
                            ctx.scoped_column(join.selectable, node.value.model_field_name),
                            node.metadata.data.order_by,
                        )
                        for node in join.order_nodes
                        if node.metadata.data.order_by
                    ]
                )
        return order_by_spec


@dataclass(frozen=True)
class ProjectionPlan:
    """Projection columns, ORM load options, selection aggregation joins, and hook specs."""

    columns: tuple[ColumnElement[Any], ...] = ()
    load_options: tuple[_AbstractLoad, ...] = ()
    aggregation_joins: tuple[Join, ...] = ()
    hook_specs: tuple[HookSpec, ...] = ()
    referenced_functions: frozenset[QueryNodeType] = frozenset()
    """Function nodes referenced in the projection selection (for subquery hoist)."""
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Maps each transform node to its labelled projection column (for column_map)."""

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any], agg_plan: AggregationPlan) -> ProjectionPlan:
        """Collects projection columns, ORM load options, aggregation joins, and hook specs.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``hook_applier`` read here).
            agg_plan: The pre-built aggregation plan providing function columns.

        Returns:
            A ProjectionPlan with columns, load options, aggregation joins, hooks,
            referenced functions, and the transform map.
        """
        selection_tree = query_graph.resolved_selection_tree()

        root_columns, column_transforms = context.aliases.inspect(selection_tree).columns()
        projection_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
        transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
            transform.node: transform.attribute for transform in column_transforms
        }
        hook_specs: list[HookSpec] = [
            HookSpec(node=selection_tree.root, alias=context.aliases.root_alias, loading_mode="undefer")
        ]
        aggregation_joins: list[Join] = []
        emitted_agg_joins: set[QueryNodeType] = set()

        for node in selection_tree.iter_depth_first():
            if node.value.is_aggregate:
                agg_columns, new_join = agg_plan.upsert(node, emitted_agg_joins)
                projection_columns.extend(agg_columns)
                if new_join is not None:
                    aggregation_joins.append(new_join)

        referenced_functions = frozenset(
            node for node in selection_tree.leaves(iteration_mode="breadth_first") if node.value.is_function
        )

        load_options: list[_AbstractLoad] = [load_only(*root_columns)] if root_columns else []
        load_options.extend(context.hook_applier.collect_load_options(selection_tree.root, context.aliases.root_alias))
        for child in selection_tree.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            child_load = cls._collect_child_load(child, context)
            projection_columns.extend(child_load.transform_columns)
            load_options.append(child_load.load)
            hook_specs.extend(child_load.hook_specs)
            transform_map.update(child_load.transform_map)

        return cls(
            columns=tuple(projection_columns),
            load_options=tuple(load_options),
            aggregation_joins=tuple(aggregation_joins),
            hook_specs=tuple(hook_specs),
            referenced_functions=referenced_functions,
            transform_map=transform_map,
        )

    @staticmethod
    def _collect_child_load(node: QueryNodeType, context: PlanContext[Any]) -> ChildLoad:
        """Collects a child relation's transform columns, eager-load option, and hook specs.

        Args:
            node: The relation node to collect loads for.
            context: The shared planning context (``aliases``, ``hook_applier`` read here).

        Returns:
            A ChildLoad with the subtree's transform columns, eager-load option, outer hook specs,
            and the node->label map for the subtree's transform columns.
        """
        ctx = context.aliases
        columns, column_transforms = ctx.inspect(node).columns()
        transform_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
        transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
            transform.node: transform.attribute for transform in column_transforms
        }
        eager_options: list[_AbstractLoad] = [load_only(*columns)] if columns else []
        node_alias = ctx.alias_from_relation_node(node, "target")
        eager_options.extend(context.hook_applier.collect_load_options(node, node_alias))
        load = contains_eager(ctx.aliased_attribute(node)).options(*eager_options)
        hook_specs: list[HookSpec] = [HookSpec(node=node, alias=node_alias, loading_mode="undefer")]
        for child in node.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            child_load = ProjectionPlan._collect_child_load(child, context)
            transform_columns.extend(child_load.transform_columns)
            load = load.options(child_load.load)
            hook_specs.extend(child_load.hook_specs)
            transform_map.update(child_load.transform_map)

        return ChildLoad(
            transform_columns=tuple(transform_columns),
            load=load,
            hook_specs=tuple(hook_specs),
            transform_map=transform_map,
        )


@dataclass(frozen=True)
class ChildLoad:
    """A child relation's collected projection columns, eager-load option, and hook specs.

    Attributes:
        transform_columns: JSON/column transform columns contributed by this subtree, in selection order.
        load: The ``contains_eager`` loader option for this relation. Always populated by
            ``_collect_child_load``; None only for a default-constructed instance.
        hook_specs: Outer query-hook application points for this subtree.
        transform_map: Maps each transform node in this subtree to its labelled projection column.
    """

    load: _AbstractLoad
    transform_columns: tuple[ColumnElement[Any], ...] = ()
    hook_specs: tuple[HookSpec, ...] = ()
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterPhase:
    """The aggregation plan, filter plan, and subquery-tree relation joins shared by both composers.

    Attributes:
        agg_plan: The aggregation plan built once for all passes.
        filter_plan: The WHERE filter plan.
        subquery_tree_joins: The subquery-tree relation joins, excluding nodes already covered by filter joins.
    """

    agg_plan: AggregationPlan
    filter_plan: FilterPlan
    subquery_tree_joins: tuple[Join, ...] = ()


@dataclass(frozen=True)
class ProjectionPhase:
    """The root-aggregation column map and the projection plan shared by both composers.

    Attributes:
        root_agg_map: Maps each root-aggregation node to its labelled window-function column.
        projection_plan: The projection plan (columns, load options, aggregation joins, hooks).
    """

    root_agg_map: Mapping[QueryNodeType, Label[Any]]
    projection_plan: ProjectionPlan


def _plan_relation_joins(
    query_graph: QueryGraph[Any],
    context: PlanContext[Any],
    is_outer: bool = True,
    tree: QueryNodeType | None = None,
) -> tuple[Join, ...]:
    """Gathers all relation joins needed for a query tree.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context (provides ``build_join``).
        is_outer: Whether to create outer joins.
        tree: The tree to gather joins from. Defaults to ``query_graph.root_join_tree``.

    Returns:
        A tuple of Join objects for every non-computed relation child, breadth-first.
    """
    source_tree = tree if tree is not None else query_graph.root_join_tree
    joins: list[Join] = [
        context.build_join(child, is_outer)
        for child in source_tree.iter_breadth_first()
        if not child.value.is_computed and child.value.is_relation and not child.is_root
    ]
    return tuple(joins)


def _build_root_aggregations(
    query_graph: QueryGraph[Any], context: PlanContext[Any]
) -> dict[QueryNodeType, Label[Any]]:
    """Builds root aggregation window-function columns.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context (``aliases`` used for inspect/root_alias).

    Returns:
        A mapping of query node to its labelled root aggregation function
        expression, preserving the order in which aggregation children appear,
        or an empty mapping when no root aggregations are present.
    """
    ctx = context.aliases
    result: dict[QueryNodeType, Label[Any]] = {}
    if query_graph.selection_tree is None:
        return result
    selection_tree = query_graph.selection_tree
    aggregation_tree = selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
    if not aggregation_tree:
        return result
    for child in aggregation_tree.children:
        result.update(ctx.inspect(child).output_functions(ctx.root_alias, lambda func: func.over()))
    return result


def _use_distinct_rank(query_graph: QueryGraph[Any], context: PlanContext[Any]) -> bool:
    """Decides whether DISTINCT ON should be emulated via a RANK() window function.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context (``db_features``, ``deterministic_ordering``,
            ``default_order_by`` read here).

    Returns:
        True if RANK() window function should be used for DISTINCT ON, False otherwise.
    """
    if context.db_features.supports_distinct_on:
        return bool(
            query_graph.distinct_on
            and (query_graph.order_by_tree or context.deterministic_ordering or context.default_order_by)
        )
    return bool(query_graph.distinct_on)


def _build_filter_semijoin(context: PlanContext[Any]) -> FilterSemiJoin:
    """Builds the PK semi-join from the root alias to the filter-statement subquery.

    Args:
        context: The shared planning context (``aliases`` root alias/model, ``statement``).

    Returns:
        A FilterSemiJoin with the subquery alias and the PK-equality onclause.
    """
    ctx = context.aliases
    statement = context.statement
    assert statement is not None
    root_mapper = class_mapper(ctx.model)
    pk_attributes = SQLAlchemyInspector.pk_attributes(root_mapper)
    filter_alias = cast("Alias", statement.with_only_columns(*pk_attributes).subquery().alias())
    onclause = and_(*[getattr(ctx.root_alias, attr.key) == filter_alias.c[attr.key] for attr in pk_attributes])
    return FilterSemiJoin(alias=filter_alias, onclause=onclause)


def _dedup_agg_joins(joins: list[Join]) -> list[Join]:
    """Deduplicates aggregation joins by node, preserving first-seen order.

    Relation joins (non-AggregationJoin) are kept as-is.  Aggregation joins are
    included at most once per aggregation node — the first occurrence wins.

    Args:
        joins: The assembled join list (relation joins + aggregation joins from all
            passes in order: filter, order, projection).

    Returns:
        A deduplicated join list with the same relative order.
    """
    seen_agg_nodes: set[QueryNodeType] = set()
    result: list[Join] = []
    for join in joins:
        if isinstance(join, AggregationJoin):
            if join.node in seen_agg_nodes:
                continue
            seen_agg_nodes.add(join.node)
        result.append(join)
    return result


def _referenced_function_nodes(filter_plan: FilterPlan, order: OrderPlan, proj: ProjectionPlan) -> list[QueryNodeType]:
    """Computes the function nodes hoisted into the pagination/distinct subquery.

    The hoisted set is the function nodes appearing in both WHERE and the selection,
    plus every function node used in ORDER BY.  Order is deterministic —
    WHERE∩selection first (in selection traversal order), then the remaining ORDER BY
    nodes — so the columns selected into the subquery and the columns re-projected from
    it agree on membership and order.

    Args:
        filter_plan: The inner filter pass (WHERE function references).
        order: The inner order pass (ORDER BY function references).
        proj: The inner projection pass (selection function references).

    Returns:
        The ordered list of referenced function nodes.
    """
    where_and_selection = filter_plan.referenced_functions & proj.referenced_functions
    referenced: list[QueryNodeType] = [node for node in proj.referenced_functions if node in where_and_selection]
    referenced.extend(node for node in order.referenced_functions if node not in where_and_selection)
    return referenced


def _assemble_inner_statement(
    query_graph: QueryGraph[Any],
    context: PlanContext[Any],
    *,
    inner_alias: AliasedClass[Any],
    distinct_on: DistinctOn,
    use_distinct_on: bool,
    inner_joins: Sequence[Join],
    where: Sequence[ColumnElement[bool]],
    order_expressions: Sequence[UnaryExpression[Any]],
    selected_function_columns: Sequence[ColumnElement[Any]],
    limit: int | None,
    offset: int | None,
) -> tuple[Select[Any], KeyedColumnElement[Any] | None]:
    """Assembles the inner pagination/distinct subquery SELECT.

    Selects the root selection columns, order-by columns, root-aggregation argument
    columns and the hoisted aggregation function columns, then applies the optional
    filter semi-join, joins, WHERE, ORDER BY, native DISTINCT ON, and LIMIT/OFFSET,
    finally replaying the in-subquery hooks.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context (``aliases``, ``hook_applier``, ``statement`` read here).
        inner_alias: The fresh root alias the subquery selects from.
        distinct_on: The DISTINCT ON configuration for the subquery.
        use_distinct_on: Whether native DISTINCT ON applies (False ⇒ rank emulation).
        inner_joins: The deduplicated inner joins (relation + aggregation).
        where: The inner WHERE predicates.
        order_expressions: The built inner ORDER BY expressions.
        selected_function_columns: The hoisted aggregation function columns.
        limit: Optional pagination limit.
        offset: Optional pagination offset.

    Returns:
        A tuple of the assembled inner statement and the anonymous rank-column label
        (``None`` when DISTINCT ON is not emulated via a window rank).
    """
    only_columns: list[Any] = [
        *context.aliases.inspect(query_graph.root_join_tree).selection(inner_alias),
        *[context.aliases.aliased_attribute(node) for node in query_graph.order_by_nodes if not node.value.is_computed],
    ]
    if aggregation_tree := query_graph.root_aggregation_tree():
        only_columns.extend(
            context.aliases.aliased_attribute(child)
            for child in aggregation_tree.leaves()
            if child.value.is_function_arg
        )
    only_columns.extend(selected_function_columns)

    rank_label: KeyedColumnElement[Any] | None = None
    if distinct_on and not use_distinct_on:
        rank_label = (
            func.row_number()
            .over(partition_by=distinct_on.expressions, order_by=list(order_expressions) or None)
            .label(None)
        )
        only_columns.append(rank_label)

    inner_statement = select(inspect(inner_alias)).options(raiseload("*")).with_only_columns(*only_columns)
    # Filtered + paginated gets: restrict the subquery to filter-visible rows via a PK
    # semi-join, so LIMIT/OFFSET count only those rows.
    if context.statement is not None:
        semijoin = _build_filter_semijoin(context)
        inner_statement = inner_statement.join(semijoin.alias, onclause=semijoin.onclause)
    for join in sorted(inner_joins):
        inner_statement = inner_statement.join(join.target, onclause=join.onclause, isouter=join.is_outer)
    if where:
        inner_statement = inner_statement.where(*where)
    if order_expressions:
        inner_statement = inner_statement.order_by(*order_expressions)
    if use_distinct_on and distinct_on:
        inner_statement = inner_statement.add_columns(
            *[
                expression.element
                for expression in order_expressions
                if not any(selected.compare(expression.element) for selected in inner_statement.selected_columns)
            ]
        )
        inner_statement = inner_statement.distinct(*distinct_on.expressions)
    if limit is not None:
        inner_statement = inner_statement.limit(limit)
    if offset is not None:
        inner_statement = inner_statement.offset(offset)
    inner_statement, _ = context.hook_applier.apply(
        inner_statement,
        node=query_graph.root_join_tree.root,
        alias=context.aliases.root_alias,
        loading_mode="add",
        in_subquery=True,
    )
    return inner_statement, rank_label


def _plan_filter_phase(query_graph: QueryGraph[Any], context: PlanContext[Any], allow_null: bool) -> FilterPhase:
    """Builds the aggregation plan, the WHERE filter plan, and the subquery-tree joins.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context.
        allow_null: Whether to allow null values in filter conditions.

    Returns:
        A FilterPhase with the aggregation plan, filter plan, and filtered subquery-tree joins.
    """
    agg_plan = AggregationPlan.plan(query_graph, context)
    filter_plan = FilterPlan.plan(query_graph, context, agg_plan, allow_null)
    filter_join_nodes = {join.node for join in filter_plan.joins}
    subquery_tree_joins: list[Join] = []
    if query_graph.subquery_join_tree:
        subquery_tree_joins = [
            join
            for join in _plan_relation_joins(query_graph, context, is_outer=True, tree=query_graph.subquery_join_tree)
            if join.node not in filter_join_nodes
        ]
    return FilterPhase(agg_plan=agg_plan, filter_plan=filter_plan, subquery_tree_joins=tuple(subquery_tree_joins))


def _plan_projection_phase(
    query_graph: QueryGraph[Any], context: PlanContext[Any], agg_plan: AggregationPlan
) -> ProjectionPhase:
    """Builds the root-aggregation window columns and the projection plan.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context.
        agg_plan: The aggregation plan supplying function columns.

    Returns:
        A ProjectionPhase with the root-aggregation column map and the projection plan.
    """
    root_agg_map: dict[QueryNodeType, Label[Any]] = {}
    if query_graph.selection_tree and query_graph.selection_tree.graph_metadata.metadata.root_aggregations:
        root_agg_map = _build_root_aggregations(query_graph, context)
    projection_plan = ProjectionPlan.plan(query_graph, context, agg_plan)
    return ProjectionPhase(root_agg_map=root_agg_map, projection_plan=projection_plan)


def _plan_subquery(
    query_graph: QueryGraph[Any],
    context: PlanContext[Any],
    *,
    limit: int | None,
    offset: int | None,
    allow_null: bool,
    distinct_on_rank: bool,
) -> QueryPlan:
    """Plans the root pagination/distinct-rank subquery boundary.

    The inner statement is assembled selecting from a fresh root alias
    (pagination/distinct happen inside it); the outer query joins the materialized
    subquery and re-projects the hoisted aggregation columns onto it.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context.
        limit: Optional pagination limit (consumed inside the subquery).
        offset: Optional pagination offset (consumed inside the subquery).
        allow_null: Whether to allow null values in filter conditions.
        distinct_on_rank: Whether DISTINCT ON is emulated via a window rank column.

    Returns:
        The flat outer ``QueryPlan`` selecting from the materialized subquery.
    """
    model = context.aliases.model
    name = model.__tablename__

    # Phase 0: re-root onto a fresh inner alias so all inner passes and the
    # build_join (which closes over the scope) build against the subquery's FROM.
    inner_alias = cast("AliasedClass[Any]", aliased(class_mapper(model), name=name, flat=True))
    context.aliases.replace(alias=inner_alias)

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    # Phase 1: inner passes against the inner alias.
    phase = _plan_filter_phase(query_graph, context, allow_null)
    agg_plan, filt = phase.agg_plan, phase.filter_plan
    subquery_tree_joins = list(phase.subquery_tree_joins)

    inner_order = OrderPlan.plan(
        query_graph,
        context,
        agg_plan,
        [*filt.joins, *subquery_tree_joins],
    )

    # Inner projection: needed only for the set of selection function references so the
    # right aggregation columns are hoisted into the subquery (its columns are discarded).
    inner_proj = ProjectionPlan.plan(query_graph, context, agg_plan)
    referenced_functions = _referenced_function_nodes(filt, inner_order, inner_proj)

    # Phase 2: assemble the inner subquery statement.
    inner_joins = _dedup_agg_joins([*filt.joins, *inner_order.joins, *subquery_tree_joins])
    selected_function_labels = {fn: agg_plan.columns[fn] for fn in referenced_functions}
    inner_statement, rank_label = _assemble_inner_statement(
        query_graph,
        context,
        inner_alias=inner_alias,
        distinct_on=distinct_on,
        use_distinct_on=use_distinct_on,
        inner_joins=inner_joins,
        where=filt.where,
        order_expressions=inner_order.expressions,
        selected_function_columns=tuple(selected_function_labels.values()),
        limit=limit,
        offset=offset,
    )

    subquery = inner_statement.subquery(name)
    outer_alias = cast("AliasedClass[Any]", aliased(class_mapper(model), subquery, name=name))

    # Phase 3: re-root onto the materialized subquery and build the outer query.
    context.aliases.replace(alias=outer_alias)

    # Re-point hoisted aggregation columns onto the subquery and drop their joins from
    # the outer agg plan: every aggregation lateral/CTE that fed a hoisted column was
    # emitted inside the subquery and must not be re-joined at the outer level.
    reprojected_agg_columns: dict[QueryNodeType, ColumnElement[Any]] = {
        fn: require_corresponding_column(subquery, cast("KeyedColumnElement[Any]", selected_function_labels[fn]))
        for fn in referenced_functions
    }
    inner_emitted_agg_nodes = {j.node for j in inner_joins if isinstance(j, AggregationJoin)}
    outer_agg_plan = AggregationPlan(
        columns={**agg_plan.columns, **reprojected_agg_columns},
        joins=tuple(j for j in agg_plan.joins if j.node not in inner_emitted_agg_nodes),
        aliases=agg_plan.aliases,
        node_functions=agg_plan.node_functions,
    )

    outer_joins = list(_plan_relation_joins(query_graph, context, is_outer=True))
    outer_order = OrderPlan.plan(
        query_graph,
        context,
        outer_agg_plan,
        outer_joins,
    )
    outer_joins.extend(outer_order.joins)

    projection_phase = _plan_projection_phase(query_graph, context, outer_agg_plan)
    root_agg_map = projection_phase.root_agg_map
    root_aggs = tuple(root_agg_map.values())
    outer_proj = projection_phase.projection_plan
    outer_joins.extend(outer_proj.aggregation_joins)

    where: tuple[ColumnElement[bool], ...] = ()
    if distinct_on_rank and rank_label is not None:
        where = (require_corresponding_column(subquery, rank_label) == 1,)

    column_map: dict[QueryNodeType, ColumnElement[Any]] = {
        **outer_agg_plan.columns,
        **outer_proj.transform_map,
        **root_agg_map,
    }

    return QueryPlan(
        root=outer_alias,
        filter_semijoin=None,
        projection_columns=outer_proj.columns,
        load_options=outer_proj.load_options,
        where=where,
        order_by=outer_order.expressions,
        joins=tuple(_dedup_agg_joins(outer_joins)),
        root_aggregation_functions=root_aggs,
        distinct_on=(),
        use_distinct_on=False,
        limit=None,
        offset=None,
        hook_specs=outer_proj.hook_specs,
        hook_applier=context.hook_applier,
        column_map=column_map,
    )


def plan_query(
    query_graph: QueryGraph[Any],
    context: PlanContext[Any],
    *,
    limit: int | None = None,
    offset: int | None = None,
    allow_null: bool = False,
) -> QueryPlan:
    """Composes the planning passes into a QueryPlan.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context.
        limit: Optional pagination limit.
        offset: Optional pagination offset.
        allow_null: Whether to allow null values in filter conditions.

    Returns:
        The assembled ``QueryPlan``.
    """
    distinct_on_rank = _use_distinct_rank(query_graph, context)

    subquery_needed = context.aliases.is_root and (limit is not None or offset is not None or distinct_on_rank)
    if subquery_needed:
        return _plan_subquery(
            query_graph,
            context,
            limit=limit,
            offset=offset,
            allow_null=allow_null,
            distinct_on_rank=distinct_on_rank,
        )

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    phase = _plan_filter_phase(query_graph, context, allow_null)
    aggregation_plan, filter_plan = phase.agg_plan, phase.filter_plan
    subquery_join_nodes = {join.node for join in filter_plan.joins}
    subquery_tree_joins = list(phase.subquery_tree_joins)

    root_tree_joins: list[Join] = [
        join
        for join in _plan_relation_joins(query_graph, context, is_outer=True)
        if join.node not in subquery_join_nodes
    ]

    all_relation_joins: list[Join] = [*filter_plan.joins, *subquery_tree_joins, *root_tree_joins]

    order = OrderPlan.plan(query_graph, context, aggregation_plan, all_relation_joins)

    projection_phase = _plan_projection_phase(query_graph, context, aggregation_plan)
    root_agg_map = projection_phase.root_agg_map
    root_aggs: tuple[Label[Any], ...] = tuple(root_agg_map.values())
    projection_plan = projection_phase.projection_plan

    pre_dedup_joins: list[Join] = [
        *filter_plan.joins,
        *order.joins,
        *subquery_tree_joins,
        *root_tree_joins,
        *projection_plan.aggregation_joins,
    ]

    deduped_joins = _dedup_agg_joins(pre_dedup_joins)

    filter_semijoin: FilterSemiJoin | None = None
    if context.statement is not None:
        filter_semijoin = _build_filter_semijoin(context)

    column_map: dict[QueryNodeType, ColumnElement[Any]] = {
        **aggregation_plan.columns,
        **projection_plan.transform_map,
        **root_agg_map,
    }

    return QueryPlan(
        root=context.aliases.root_alias,
        filter_semijoin=filter_semijoin,
        projection_columns=projection_plan.columns,
        load_options=projection_plan.load_options,
        where=filter_plan.where,
        order_by=order.expressions,
        joins=tuple(deduped_joins),
        root_aggregation_functions=root_aggs,
        distinct_on=(cast("tuple[ColumnElement[Any], ...]", tuple(distinct_on.expressions)) if distinct_on else ()),
        use_distinct_on=use_distinct_on,
        limit=limit,
        offset=offset,
        hook_specs=projection_plan.hook_specs,
        hook_applier=context.hook_applier,
        column_map=column_map,
    )
