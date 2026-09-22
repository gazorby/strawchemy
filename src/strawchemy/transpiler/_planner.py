"""Builds a QueryPlan from a QueryGraph through composable planning passes.

Each pass — AggregationPlan, FilterPlan, OrderPlan, ProjectionPlan — exposes a ``plan()``
classmethod returning an immutable result; ``plan_query`` composes them into a ``QueryPlan``.
SQLAlchemy statements are assembled only by ``QueryPlan.emit``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy import and_, exists, func, inspect, not_, null, or_, select, true, tuple_
from sqlalchemy.orm import Mapper, RelationshipProperty, aliased, class_mapper, contains_eager, load_only, raiseload
from sqlalchemy.sql.functions import count as sqla_count
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.dto.strawberry import (
    AggregationFilter,
    CustomFilter,
    Filter,
    OrderByEnum,
    OrderByRelationFilterDTO,
    QueryNode,
    decompose_order_by,
)
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.repository.typing import DeclarativeT
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._aliasing import AliasContext, require_corresponding_column
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
from strawchemy.transpiler._strategies import correlate_relation, select_join_strategy

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
        aliases = AliasContext(model, supported_dialect, inspector=inspector)
        return cls(
            aliases=aliases,
            db_features=db_features,
            dialect=dialect,
            hook_applier=HookApplier(aliases, query_hooks or defaultdict(list)),
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
        target_alias: AliasedClass[Any] = aliased(target_mapper, flat=True)
        order_by = relation_filter.order_by if isinstance(relation_filter, OrderByRelationFilterDTO) else []

        sub_context = replace(self, aliases=self.aliases.sub(target_mapper.class_, target_alias), statement=None)
        query_graph = QueryGraph(sub_context.aliases, order_by=order_by)
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
    selection_functions: Mapping[QueryNodeType, frozenset[QueryNodeType]] = field(default_factory=dict)
    """Aggregation node -> the subset of its function nodes the selection tree asks to project."""

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        available_columns: Mapping[QueryNodeType, ColumnElement[Any]] | None = None,
    ) -> AggregationPlan:
        """Builds aggregation joins and function-column references without mutating scope.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``db_features`` read here).
            available_columns: Function columns an earlier stage already materialized; they are
                referenced as given and left out of the emitted joins, which are skipped entirely
                for an aggregation node whose functions are all covered.

        Returns:
            An ``AggregationPlan`` with columns, joins, aliases, and function-node keys.
        """
        specs = cls._accumulate_specs(query_graph, context)
        available = available_columns or {}
        columns: dict[QueryNodeType, ColumnElement[Any]] = {}
        aliases: dict[QueryNodeType, AliasedClass[Any]] = {}
        node_functions: dict[QueryNodeType, tuple[QueryNodeType, ...]] = {}
        selection_functions: dict[QueryNodeType, frozenset[QueryNodeType]] = {}
        joins: list[AggregationJoin] = []

        for aggregation_node, spec in specs.items():
            if not spec.functions:
                continue
            pending: dict[QueryNodeType, Label[Any]] = {}
            for function_node, label in spec.functions.items():
                if (reused := available.get(function_node)) is not None:
                    columns[function_node] = reused
                else:
                    pending[function_node] = label
            if pending:
                if context.db_features.supports_lateral:
                    join = cls._lateral_join(aggregation_node, pending.values(), spec.alias, context)
                else:
                    join = cls._cte_join(
                        node=aggregation_node, alias=spec.alias, statement=select(*pending.values()), context=context
                    )
                for function_node, inner_label in pending.items():
                    column = require_corresponding_column(join.selectable, inner_label)
                    is_count = isinstance(inner_label.element, sqla_count)
                    columns[function_node] = func.coalesce(column, 0) if join.is_outer and is_count else column
                joins.append(join)
            aliases[aggregation_node] = spec.alias
            node_functions[aggregation_node] = tuple(spec.functions.keys())
            selection_functions[aggregation_node] = frozenset(spec.selection_functions)

        return cls(
            columns=columns,
            joins=tuple(joins),
            aliases=aliases,
            node_functions=node_functions,
            selection_functions=selection_functions,
        )

    @staticmethod
    def _accumulate_specs(
        query_graph: QueryGraph[Any], context: PlanContext[Any]
    ) -> dict[QueryNodeType, AggregationSpec]:
        """Accumulates one AggregationSpec per aggregation node from the query graph.

        Visits sources in fixed order — filter, order-by, selection — deduplicating function
        expressions per aggregation node by their function_node key and marking the selected ones.

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
        sources = (
            *((node, False) for node in order_by_aggregations),
            *((node, True) for node in selection_aggregations),
        )
        for aggregation_node, is_selection in sources:
            spec = specs.get(aggregation_node)
            if spec is None:
                spec = specs[aggregation_node] = AggregationSpec.create(aggregation_node, aliases)
            for child_inspect in aliases.inspect(aggregation_node).children:
                for function_node, function in child_inspect.output_functions(spec.alias).items():
                    if function_node not in spec.functions:
                        spec.functions[function_node] = function
                    if is_selection:
                        spec.selection_functions.add(function_node)

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
        lateral_statement = correlate_relation(select(*function_columns), root_relation, alias).lateral()
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
        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)

        if relationship.secondary is not None:
            return AggregationPlan._secondary_cte_join(node, alias, statement, context)

        remote_fks = aliases.inspect(node).foreign_key_columns("target", alias)
        cte_statement = (
            statement.add_columns(*remote_fks)
            .group_by(*remote_fks)
            .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
            .cte()
        )
        cte_alias = aliased(alias, cte_statement)
        return AggregationJoin(
            target=cte_alias, onclause=aliases.aliased_attribute(node).of_type(cte_alias), node=node, is_outer=True
        )

    @staticmethod
    def _secondary_cte_join(
        node: QueryNodeType, alias: Any, statement: Any, context: PlanContext[Any]
    ) -> AggregationJoin:
        """Creates a CTE-based aggregation join for a relationship using a secondary table.

        The relationship is traversed from a CTE-private parent alias, so SQLAlchemy emits the
        configured ``primaryjoin`` and ``secondaryjoin`` in full rather than the foreign-key pairs
        alone. Grouping on the parent keys of that alias exports them for the outer correlation,
        which is an outer join because a parent without related rows contributes no group.

        Args:
            node: The aggregation node.
            alias: The aliased target class for the aggregation target.
            statement: The SQLAlchemy select statement selecting the aggregate functions.
            context: The shared planning context (``aliases`` provides inspect for key resolution).

        Returns:
            An AggregationJoin backed by a CTE.
        """
        aliases = context.aliases
        node_inspect = aliases.inspect(node)
        parent_node = node.find_parent(lambda parent: not parent.value.is_computed, strict=True)
        parent_alias = aliases.alias_from_relation_node(parent_node, "target")
        cte_parent_alias = aliased(inspect(parent_alias).mapper, flat=True)
        cte_keys = node_inspect.foreign_key_columns("parent", cte_parent_alias)
        cte_statement = (
            statement.select_from(cte_parent_alias)
            .join(aliases.aliased_attribute(node, cte_parent_alias).of_type(inspect(alias)))
            .add_columns(*cte_keys)
            .group_by(*cte_keys)
            .cte()
        )
        cte_alias = aliased(cte_parent_alias, cte_statement)
        onclause = and_(
            *[
                parent_key == cte_key
                for parent_key, cte_key in zip(
                    node_inspect.foreign_key_columns("parent", parent_alias),
                    node_inspect.foreign_key_columns("parent", cte_alias),
                    strict=True,
                )
            ]
        )
        return AggregationJoin(target=cte_alias, onclause=onclause, node=node, is_outer=True)

    def selected_columns_for(self, node: QueryNodeType) -> list[ColumnElement[Any]]:
        """Returns the function columns an aggregation node's selection asks for, in spec order.

        Args:
            node: The aggregation node whose function columns are requested.

        Returns:
            A list of labelled function columns in ``node_functions`` key order, or empty.
        """
        selected = self.selection_functions[node]
        return [self.columns[fn] for fn in self.node_functions[node] if fn in selected]

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
        """Returns the node's selected function columns, returning its join at most once.

        Args:
            node: The aggregation node whose columns are requested.
            emitted: Mutable set tracking already-returned aggregation joins.

        Returns:
            The resolved function columns and the join (returned at most once per node).
        """
        function_columns = self.selected_columns_for(node)
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
            A FilterPlan with WHERE predicates and joins.
        """
        if not query_graph.query_filter:
            return cls()

        emitted_agg_joins: set[QueryNodeType] = set()

        where = cls._where(
            query_graph.query_filter,
            context,
            agg_plan=agg_plan,
            emitted_agg_joins=emitted_agg_joins,
            allow_null=allow_null,
        )
        return cls(where=tuple(where.expressions), joins=tuple(where.joins))

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
    def _custom_filter_expression(custom: CustomFilter, context: PlanContext[Any]) -> ColumnElement[bool]:
        """Folds a custom-apply filter into a correlated EXISTS/IN predicate.

        Builds an isolated ``select(model)``, lets the callback mutate it, then correlates it to
        the outer query on primary-key equality so the result is a single boolean predicate that
        composes under AND/OR/NOT.

        Args:
            custom: The set custom filter value (callable, value, strategy, model node).
            context: The shared planning context (``aliases``, ``dialect`` read here).

        Returns:
            A boolean SQLAlchemy expression.
        """
        model = custom.field_node.value.model
        mapper = class_mapper(model)
        inner_pks = SQLAlchemyInspector.pk_attributes(mapper)
        outer_pks = context.aliases.aliased_id_attributes(custom.field_node)

        isolated = custom.apply(select(model), custom.value, dialect=context.dialect, model=model)

        if custom.join == "in":
            inner_select = isolated.with_only_columns(*inner_pks)
            if len(outer_pks) == 1:
                # Scalar IN is more portable/optimizable than a single-element tuple IN.
                return outer_pks[0].in_(inner_select)
            return tuple_(*outer_pks).in_(inner_select)

        outer_alias = (
            context.aliases.root_alias
            if custom.field_node.is_root
            else context.aliases.alias_from_relation_node(custom.field_node, "target")
        )

        # The outer query aliases the root model to a name equal to its table name, so the inner
        # subquery must use a distinct alias; otherwise the PK-equality correlation collapses to a
        # tautology against the same table and the EXISTS matches every outer row. An unnamed alias
        # lets SQLAlchemy generate a guaranteed-unique name (also safe for repeated/nested filters).
        inner_alias = aliased(mapper, flat=True)
        adapter = ClauseAdapter(inspect(inner_alias).selectable)
        adapted_pks = [adapter.traverse(pk.__clause_element__()) for pk in inner_pks]
        adapted_select = adapter.traverse(isolated.with_only_columns(*adapted_pks))

        correlation = and_(*[inner == outer for inner, outer in zip(adapted_pks, outer_pks, strict=True)])
        return exists(adapted_select.where(correlation)).correlate(outer_alias)

    @staticmethod
    def _aggregation_filter(
        aggregation: AggregationFilter,
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
    ) -> tuple[Join | None, list[ColumnElement[bool]]]:
        """Looks up an aggregation filter's column and builds its filter expressions.

        Args:
            aggregation: The aggregation filter to process.
            context: The shared planning context (``aliases``, ``dialect`` read here).
            agg_plan: The pre-built aggregation plan providing columns and aliases.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.

        Returns:
            A tuple of the aggregation join the first time it is needed for this node
            (``None`` otherwise) and the boolean filter expressions.
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

        return agg_join, bool_expressions

    @staticmethod
    def _gather_conjunctions(
        query: Sequence[Filter | AggregationFilter | GraphQLComparison | CustomFilter],
        context: PlanContext[Any],
        *,
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        not_null_check: bool = False,
    ) -> Conjunction:
        """Gathers all conjunctions from a sequence of filters.

        Args:
            query: A sequence of filters to gather conjunctions from.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
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
                aggregation_join, aggregation_expressions = FilterPlan._aggregation_filter(
                    value, context, agg_plan, emitted_agg_joins
                )
                if aggregation_join is not None:
                    joins.append(aggregation_join)
                bool_expressions.extend(aggregation_expressions)
            elif isinstance(value, GraphQLComparison):
                node_path = value.field_node.path_from_root()
                bool_expressions.extend(FilterPlan._to_expressions(context, value, not_null_check=not_null_check))
            elif isinstance(value, CustomFilter):
                node_path = value.field_node.path_from_root()
                bool_expressions.append(FilterPlan._custom_filter_expression(value, context))
            else:
                conjunction = FilterPlan._conjunctions(
                    value,
                    context,
                    agg_plan=agg_plan,
                    emitted_agg_joins=emitted_agg_joins,
                    allow_null=not_null_check,
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
        *,
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        allow_null: bool = False,
    ) -> Conjunction:
        """Processes a filter's AND, OR, and NOT conditions into a conjunction.

        Args:
            query: The filter to process.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A conjunction of expressions, joins, and common join path.
        """
        bool_expressions: list[ColumnElement[bool]] = []
        and_conjunction = FilterPlan._gather_conjunctions(
            query.and_,
            context,
            agg_plan=agg_plan,
            emitted_agg_joins=emitted_agg_joins,
            not_null_check=allow_null,
        )
        or_conjunction = FilterPlan._gather_conjunctions(
            query.or_,
            context,
            agg_plan=agg_plan,
            emitted_agg_joins=emitted_agg_joins,
            not_null_check=allow_null,
        )
        common_path = QueryNode.common_path(and_conjunction.common_join_path, or_conjunction.common_join_path)
        joins = [*and_conjunction.joins, *or_conjunction.joins]

        if query.not_:
            not_conjunction = FilterPlan._gather_conjunctions(
                [query.not_],
                context,
                agg_plan=agg_plan,
                emitted_agg_joins=emitted_agg_joins,
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
        *,
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        allow_null: bool = False,
    ) -> Where:
        """Creates WHERE expressions and joins from a filter.

        Args:
            query_filter: The filter to create expressions from.
            context: The shared planning context (``aliases``, ``dialect``, ``build_join`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            allow_null: Whether to allow null values in the filter conditions.

        Returns:
            A Where containing expressions and required joins.
        """
        conjunction = FilterPlan._conjunctions(
            query_filter,
            context,
            agg_plan=agg_plan,
            emitted_agg_joins=emitted_agg_joins,
            allow_null=allow_null,
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
            An OrderPlan with expressions and new relation joins.
        """
        _default_order_by = list(context.default_order_by)

        if not (query_graph.order_by_tree or context.deterministic_ordering or _default_order_by):
            return cls()

        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        joins: list[Join] = []
        emitted_agg_joins: set[QueryNodeType] = set()

        for node in query_graph.order_by_nodes:
            cls._build_node(
                node,
                context,
                agg_plan=agg_plan,
                emitted_agg_joins=emitted_agg_joins,
                columns=columns,
                joins=joins,
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

        return cls(expressions=tuple(order_by.expressions), joins=tuple(order_by.joins))

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
        aliases = context.aliases
        alias_insp = inspect(aliases.root_alias)
        column_keys = {attr.key for attr in alias_insp.mapper.column_attrs}
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
        for expr in context.default_order_by:
            decomposed = decompose_order_by(expr)
            if decomposed.key not in column_keys:  # pragma: no cover  # defensive
                msg = f"`default_order_by` column '{decomposed.key}' is not a column of {aliases.model.__name__}"
                raise StrawchemyFieldError(msg)
            aliased_attribute = alias_insp.mapper.attrs[decomposed.key].class_attribute.adapt_to_entity(alias_insp)
            columns.append((aliased_attribute, decomposed.order))
        return columns

    @staticmethod
    def _build_node(
        node: QueryNodeType,
        context: PlanContext[Any],
        *,
        agg_plan: AggregationPlan,
        emitted_agg_joins: set[QueryNodeType],
        columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]],
        joins: list[Join],
    ) -> None:
        """Processes a single order-by node, updating columns/joins/tracked sets in place.

        Extracted from ``plan`` to reduce cyclomatic complexity.

        Args:
            node: The order-by node to process.
            context: The shared planning context (``aliases`` read here).
            agg_plan: The pre-built aggregation plan.
            emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
            columns: Mutable list accumulating ``(column, order)`` pairs.
            joins: Mutable list accumulating new relation/aggregation joins.
        """
        if node.metadata.data.order_by is None:
            msg = "Missing order by value"
            raise TranspilingError(msg)
        if node.value.is_function_arg or node.value.is_function:
            first_aggregate_parent = node.find_parent(lambda n: n.value.is_aggregate, strict=True)
            if first_aggregate_parent not in emitted_agg_joins:
                emitted_agg_joins.add(first_aggregate_parent)
                if (aggregation_join := agg_plan.join_for(first_aggregate_parent)) is not None:
                    joins.append(aggregation_join)
            columns.append((agg_plan.columns[node], node.metadata.data.order_by))
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
        aliases = context.aliases
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
                    [(attribute, OrderByEnum.ASC) for attribute in aliases.aliased_id_attributes(join.node)]
                )
            elif join.order_nodes:
                order_by_spec.extend(
                    [
                        (
                            aliases.scoped_column(join.selectable, node.value.model_field_name),
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
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Maps each transform node to its labelled projection column (for column_map)."""
    identity_map: Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]] = field(default_factory=dict)
    """Maps each related level owning computed values to its primary-key projection columns."""

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any], agg_plan: AggregationPlan) -> ProjectionPlan:
        """Collects projection columns, ORM load options, aggregation joins, and hook specs.

        Args:
            query_graph: The graph representation of the query being planned.
            context: The shared planning context (``aliases``, ``hook_applier`` read here).
            agg_plan: The pre-built aggregation plan providing function columns.

        Returns:
            A ProjectionPlan with columns, load options, aggregation joins, hooks,
            and the transform map.
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

        identity_map = cls._identity_columns(selection_tree, context)
        for identity_columns in identity_map.values():
            projection_columns.extend(identity_columns)

        return cls(
            columns=tuple(projection_columns),
            load_options=tuple(load_options),
            aggregation_joins=tuple(aggregation_joins),
            hook_specs=tuple(hook_specs),
            transform_map=transform_map,
            identity_map=identity_map,
        )

    @staticmethod
    def _identity_columns(
        selection_tree: QueryNodeType, context: PlanContext[Any]
    ) -> dict[QueryNodeType, tuple[ColumnElement[Any], ...]]:
        """Collects the primary-key columns of every related level that owns computed values.

        A computed value is emitted once per flat result row, so it belongs to the related
        element the row carries, not to the row's root. Selecting that element's primary key
        alongside lets the executor attribute the value to it.

        Args:
            selection_tree: The resolved selection tree to walk.
            context: The shared planning context (``aliases`` resolves the level's alias).

        Returns:
            A mapping of relation node to its primary-key columns, in selection order.
        """
        identity_map: dict[QueryNodeType, tuple[ColumnElement[Any], ...]] = {}
        for node in selection_tree.iter_depth_first():
            if not (node.value.is_computed or node.metadata.data.is_transform):
                continue
            owner = node.find_parent(lambda parent: parent.value.is_relation and not parent.value.is_computed)
            if owner is None or owner in identity_map:
                continue
            owner_name = context.aliases.inspect(owner).name
            identity_map[owner] = tuple(
                attribute.label(f"{owner_name}__{attribute.key}")
                for attribute in context.aliases.aliased_id_attributes(owner)
            )
        return identity_map

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
        aliases = context.aliases
        columns, column_transforms = aliases.inspect(node).columns()
        transform_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
        transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
            transform.node: transform.attribute for transform in column_transforms
        }
        eager_options: list[_AbstractLoad] = [load_only(*columns)] if columns else []
        node_alias = aliases.alias_from_relation_node(node, "target")
        eager_options.extend(context.hook_applier.collect_load_options(node, node_alias))
        load = contains_eager(aliases.aliased_attribute(node)).options(*eager_options)
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
        root_aggregations_map: Maps each root-aggregation node to its labelled window-function column.
        projection_plan: The projection plan (columns, load options, aggregation joins, hooks).
    """

    root_aggregations_map: Mapping[QueryNodeType, Label[Any]]
    projection_plan: ProjectionPlan


def _plan_relation_joins(
    query_graph: QueryGraph[Any], context: PlanContext[Any], is_outer: bool = True, tree: QueryNodeType | None = None
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


def _use_distinct_rank(query_graph: QueryGraph[Any], context: PlanContext[Any]) -> bool:
    """Decides whether DISTINCT ON should be emulated via a window rank function.

    On dialects with native ``DISTINCT ON`` (PostgreSQL), emulation is only needed when
    ordering is present *and* the distinct-on fields are not the leftmost ORDER BY columns.
    With no ordering, or with a compatible prefix ordering, native DISTINCT ON is used. On
    dialects without native support, any distinct clause is emulated.

    Args:
        query_graph: The graph representation of the query being planned.
        context: The shared planning context (``db_features``, ``deterministic_ordering``,
            ``default_order_by`` read here).

    Returns:
        True if a RANK/row_number window emulation should be used, False for native/none.
    """
    if not context.db_features.supports_distinct_on:
        return bool(query_graph.distinct_on)
    if not query_graph.distinct_on:
        return False
    has_ordering = bool(query_graph.order_by_tree or context.deterministic_ordering or context.default_order_by)
    if not has_ordering:
        return False
    # Native DISTINCT ON requires the distinct-on fields to be the leftmost ORDER BY
    # columns, in order; otherwise fall back to row_number emulation.
    distinct_fields = [enum.field_definition for enum in query_graph.distinct_on]
    order_nodes = query_graph.order_by_nodes
    if len(order_nodes) < len(distinct_fields):
        return True
    is_order_prefix = all(
        order_nodes[index].value.model_field is field.model_field for index, field in enumerate(distinct_fields)
    )
    return not is_order_prefix


@dataclass(frozen=True)
class UserStatementPlan:
    """Encapsulates applying a user-provided base ``filter_statement``.

    A user statement is applied either by inlining its WHERE predicates directly (when the
    statement is a plain WHERE-only select of the root model) or, otherwise, via a
    primary-key semi-join to the statement reduced to its primary-key columns.

    Attributes:
        statement: The user-provided base filter statement.
        aliases: The query scope, providing the root model and root alias.
    """

    statement: Select[Any]
    aliases: AliasContext[Any]

    def is_trivial(self) -> bool:
        """Decides whether the statement is a plain WHERE-only select of the root model.

        Compares the statement (public ``ClauseElement.compare``) against a canonical
        ``select(model).where(whereclause)``. Any additional clause — join, GROUP BY,
        DISTINCT, HAVING, LIMIT, OFFSET, ORDER BY — makes the comparison fail, leaving the
        statement to the semi-join path.

        A statement's ``execution_options`` are not preserved when inlined; the emitted SQL
        is identical, but non-SQL driver hints attached to the filter statement are dropped.

        Returns:
            True if the statement can be inlined as direct WHERE predicates.
        """
        canonical = select(self.aliases.model)
        where = self.statement.whereclause
        if where is not None:
            canonical = canonical.where(where)
        try:
            return self.statement.compare(canonical)
        except AttributeError:  # uncomparable statement → fall back to the semi-join path
            return False

    def inline_where(self, alias: AliasedClass[Any]) -> ColumnElement[bool] | None:
        """Adapts the statement's WHERE predicate onto ``alias``.

        The base statement references the model's base-table columns; the main query selects
        from an aliased root, so the predicate is rewritten to bind to that alias.

        Args:
            alias: The aliased entity the main query selects from.

        Returns:
            The adapted WHERE predicate, or None when the statement has no WHERE clause.
        """
        where = self.statement.whereclause
        if where is None:
            return None
        adapter = ClauseAdapter(inspect(alias).selectable)
        return adapter.traverse(where)

    def semijoin(self) -> FilterSemiJoin:
        """Builds the PK semi-join from the root alias to the filter-statement subquery.

        Returns:
            A FilterSemiJoin with the subquery alias and the PK-equality onclause.
        """
        root_mapper = class_mapper(self.aliases.model)
        pk_attributes = SQLAlchemyInspector.pk_attributes(root_mapper)
        filter_alias = cast("Alias", self.statement.with_only_columns(*pk_attributes).subquery().alias())
        on_clause = and_(
            *[getattr(self.aliases.root_alias, attr.key) == filter_alias.c[attr.key] for attr in pk_attributes]
        )
        return FilterSemiJoin(alias=filter_alias, onclause=on_clause)

    def apply_to_statement(self, statement: Select[Any], alias: AliasedClass[Any]) -> Select[Any]:
        """Applies the user statement to a select being assembled (subquery path).

        Owns the inline-vs-semijoin decision so call sites do not branch: a trivial
        statement's WHERE is inlined onto ``alias``; otherwise the PK semi-join is joined in.

        Args:
            statement: The select being assembled.
            alias: The aliased root the statement selects from.

        Returns:
            The statement with the user filter applied.
        """
        if not self.is_trivial():
            semijoin = self.semijoin()
            return statement.join(semijoin.alias, onclause=semijoin.onclause)
        where = self.inline_where(alias)
        return statement.where(where) if where is not None else statement


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


def _clause_element(column: ColumnElement[Any]) -> ColumnElement[Any]:
    """Returns the underlying clause element for a column, unwrapping ORM attributes.

    ``InstrumentedAttribute`` wraps a ``ColumnElement`` via ``__clause_element__()``; calling
    ``.compare()`` on the attribute directly does not delegate to the underlying element, so
    two attributes that map to the same column but were constructed via different access paths
    (e.g. ``getattr(alias, key)`` vs ``field.adapt_to_entity(insp)``) incorrectly compare as
    unequal.  Unwrapping to the ``AnnotatedColumn`` level gives correct structural equality.

    Args:
        column: A column or ORM attribute to unwrap.

    Returns:
        The underlying ``ColumnElement``.
    """
    if hasattr(column, "__clause_element__"):
        return column.__clause_element__()
    return column


def _dedup_columns(columns: Sequence[ColumnElement[Any]]) -> list[ColumnElement[Any]]:
    """Removes structurally duplicate columns, preserving first-seen order.

    The inner subquery accumulates projection columns from several sources (selection,
    order-by nodes, root-aggregation arguments). A column reached through more than one
    source is the same expression but a distinct object, which SQLAlchemy would otherwise
    emit twice with an auto-suffixed label (``id`` and ``id__1``).

    Args:
        columns: The assembled projection columns, in selection order.

    Returns:
        The columns with later structural duplicates dropped.
    """
    unique: list[ColumnElement[Any]] = []
    for column in columns:
        col_elem = _clause_element(column)
        if not any(col_elem is _clause_element(seen) or col_elem.compare(_clause_element(seen)) for seen in unique):
            unique.append(column)
    return unique


def _referenced_function_nodes(agg_plan: AggregationPlan, inner_joins: Sequence[Join]) -> list[QueryNodeType]:
    """Computes the function nodes hoisted into the pagination/distinct subquery.

    Hoisting is all-or-nothing per aggregation node: a node the subquery already joins
    materializes every one of its functions anyway, so all of them are selected out and
    re-projected, and the outer query drops the join instead of computing the same
    aggregate twice. A node with no inner join stays outside, where it is computed over
    the page rather than over the whole filtered set.

    Args:
        agg_plan: The inner aggregation pass, mapping each node to its function nodes.
        inner_joins: The deduplicated inner joins, in emission order.

    Returns:
        The ordered list of referenced function nodes.
    """
    return [
        function
        for join in inner_joins
        if isinstance(join, AggregationJoin)
        for function in agg_plan.node_functions.get(join.node, ())
    ]


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
    # Hoisted columns skip the dedup: unique by function node, and two anonymous columns of one join compare equal.
    projected: list[Any] = [*_dedup_columns(only_columns), *selected_function_columns]

    rank_label: KeyedColumnElement[Any] | None = None
    if distinct_on and not use_distinct_on:
        rank_label = (
            func.row_number()
            .over(partition_by=distinct_on.expressions, order_by=list(order_expressions) or None)
            .label(None)
        )
        projected.append(rank_label)

    inner_statement = select(inspect(inner_alias)).options(raiseload("*")).with_only_columns(*projected)
    # Filtered + paginated gets: restrict the subquery to filter-visible rows; a trivial
    # statement inlines the WHERE directly, otherwise a PK semi-join is used.
    if context.statement is not None:
        inner_statement = UserStatementPlan(context.statement, context.aliases).apply_to_statement(
            inner_statement, inner_alias
        )
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
    aggregation_plan = AggregationPlan.plan(query_graph, context)
    filter_plan = FilterPlan.plan(query_graph, context, aggregation_plan, allow_null)
    filter_join_nodes = {join.node for join in filter_plan.joins}
    subquery_tree_joins: list[Join] = []
    if query_graph.subquery_join_tree:
        subquery_tree_joins = [
            join
            for join in _plan_relation_joins(query_graph, context, is_outer=True, tree=query_graph.subquery_join_tree)
            if join.node not in filter_join_nodes
        ]
    return FilterPhase(
        agg_plan=aggregation_plan, filter_plan=filter_plan, subquery_tree_joins=tuple(subquery_tree_joins)
    )


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
    root_aggregations_map: dict[QueryNodeType, Label[Any]] = {}
    selection_tree = query_graph.selection_tree
    if selection_tree is not None and selection_tree.graph_metadata.metadata.root_aggregations:
        aggregation_tree = selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        if aggregation_tree:
            for child in aggregation_tree.children:
                root_aggregations_map.update(
                    context.aliases.inspect(child).output_functions(
                        context.aliases.root_alias, lambda func: func.over()
                    )
                )
    projection_plan = ProjectionPlan.plan(query_graph, context, agg_plan)
    return ProjectionPhase(root_aggregations_map=root_aggregations_map, projection_plan=projection_plan)


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
    inner_alias = aliased(class_mapper(model), name=name, flat=True)
    context.aliases.replace(alias=inner_alias)

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    # Phase 1: inner passes against the inner alias.
    phase = _plan_filter_phase(query_graph, context, allow_null)
    aggregation_plan, filter_plan = phase.agg_plan, phase.filter_plan
    subquery_tree_joins = list(phase.subquery_tree_joins)

    inner_order = OrderPlan.plan(query_graph, context, aggregation_plan, [*filter_plan.joins, *subquery_tree_joins])

    # Phase 2: assemble the inner subquery statement.
    inner_joins = _dedup_agg_joins([*filter_plan.joins, *inner_order.joins, *subquery_tree_joins])
    referenced_functions = _referenced_function_nodes(aggregation_plan, inner_joins)
    selected_function_labels = {fn: aggregation_plan.columns[fn] for fn in referenced_functions}
    inner_statement, rank_label = _assemble_inner_statement(
        query_graph,
        context,
        inner_alias=inner_alias,
        distinct_on=distinct_on,
        use_distinct_on=use_distinct_on,
        inner_joins=inner_joins,
        where=filter_plan.where,
        order_expressions=inner_order.expressions,
        selected_function_columns=tuple(selected_function_labels.values()),
        limit=limit,
        offset=offset,
    )

    subquery = inner_statement.subquery(name)
    outer_alias = aliased(class_mapper(model), subquery, name=name)

    # Phase 3: re-root onto the materialized subquery and build the outer query.
    context.aliases.replace(alias=outer_alias)

    # Rebuild aggregation joins against the materialized subquery. The inner plan was
    # built while the scope pointed at ``inner_alias``; reusing a selection-only join
    # here would pull that alias back into the outer FROM alongside the subquery.
    reprojected_agg_columns: dict[QueryNodeType, ColumnElement[Any]] = {
        fn: require_corresponding_column(subquery, cast("KeyedColumnElement[Any]", selected_function_labels[fn]))
        for fn in referenced_functions
    }
    outer_agg_plan = AggregationPlan.plan(query_graph, context, reprojected_agg_columns)

    outer_joins = list(_plan_relation_joins(query_graph, context, is_outer=True))
    outer_order = OrderPlan.plan(query_graph, context, outer_agg_plan, outer_joins)
    outer_joins.extend(outer_order.joins)

    projection_phase = _plan_projection_phase(query_graph, context, outer_agg_plan)
    root_agg_map = projection_phase.root_aggregations_map
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
        identity_columns=outer_proj.identity_map,
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
            query_graph, context, limit=limit, offset=offset, allow_null=allow_null, distinct_on_rank=distinct_on_rank
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
    root_aggregations_map = projection_phase.root_aggregations_map
    root_aggregations: tuple[Label[Any], ...] = tuple(root_aggregations_map.values())
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
    where_predicates: tuple[ColumnElement[bool], ...] = filter_plan.where
    if context.statement is not None:
        user_statement = UserStatementPlan(context.statement, context.aliases)
        if user_statement.is_trivial():
            inlined = user_statement.inline_where(context.aliases.root_alias)
            if inlined is not None:
                where_predicates = (*where_predicates, inlined)
        else:
            filter_semijoin = user_statement.semijoin()

    column_map: dict[QueryNodeType, ColumnElement[Any]] = {
        **aggregation_plan.columns,
        **projection_plan.transform_map,
        **root_aggregations_map,
    }

    return QueryPlan(
        root=context.aliases.root_alias,
        filter_semijoin=filter_semijoin,
        projection_columns=projection_plan.columns,
        load_options=projection_plan.load_options,
        where=where_predicates,
        order_by=order.expressions,
        joins=tuple(deduped_joins),
        root_aggregation_functions=root_aggregations,
        distinct_on=(cast("tuple[ColumnElement[Any], ...]", tuple(distinct_on.expressions)) if distinct_on else ()),
        use_distinct_on=use_distinct_on,
        limit=limit,
        offset=offset,
        hook_specs=projection_plan.hook_specs,
        hook_applier=context.hook_applier,
        column_map=column_map,
        identity_columns=projection_plan.identity_map,
    )
