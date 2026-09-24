"""Turns a QueryGraph into a QueryPlan.

``plan_query`` runs one planning pass per concern (aggregation, filter, order, projection) and combines their
immutable results into a ``QueryPlan``. Only ``QueryPlan.emit`` builds the SQLAlchemy statement.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Generic, Protocol, cast

from sqlalchemy import and_, exists, func, inspect, not_, null, or_, select, true, tuple_
from sqlalchemy.orm import Mapper, RelationshipProperty, aliased, class_mapper, contains_eager, load_only, raiseload
from sqlalchemy.sql.functions import count as sqla_count
from sqlalchemy.sql.util import ClauseAdapter
from typing_extensions import ParamSpec, Self

from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.dto.strawberry import (
    AggregationFilter,
    CustomFilter,
    Filter,
    OrderByEnum,
    QueryNode,
    decompose_order_by,
)
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.repository.typing import DeclarativeT
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._aliasing import AliasContext, require_corresponding_column, same_column
from strawchemy.transpiler._plan import FilterSemiJoin, HookSpec, QueryPlan, add_missing_columns
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

__all__ = ("AggregationPlan", "FilterPlan", "OrderPlan", "Plan", "PlanContext", "ProjectionPlan", "plan_query")

_P = ParamSpec("_P")


class Plan(Protocol[_P]):
    """A planning pass that returns an immutable result for one query graph."""

    @classmethod
    def plan(
        cls, query_graph: QueryGraph[Any], context: PlanContext[Any], *args: _P.args, **kwargs: _P.kwargs
    ) -> Self: ...


@dataclass(frozen=True)
class PlanContext(Generic[DeclarativeT]):
    """Settings and helpers shared by every planning pass of one query.

    Built once for the root query; ``build_join`` derives a copy for each relation that gets its own plan.
    """

    aliases: AliasContext[DeclarativeT]
    """Aliases of the query; ``_plan_subquery`` swaps its root alias in place."""
    db_features: DatabaseFeatures
    """Features the target database supports."""
    dialect: Dialect
    hook_applier: HookApplier
    """Applies query hooks and collects their load options."""
    join_strategy: JoinStrategy
    """Builds relation joins as LATERAL or CTE, depending on ``db_features``."""
    default_order_by: tuple[OrderByExpr, ...] = ()
    """Ordering used when the client asks for none."""
    deterministic_ordering: bool = False
    """Adds primary-key columns to ORDER BY so that row order is stable."""
    statement: Select[Any] | None = None
    """User filter statement restricting the root rows."""

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
        """Builds the context of a root query on ``model``."""
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
        """Builds the join from the current query to the relation behind ``node``.

        A relation without its own filter, ordering or pagination, whose query hooks only filter, is a plain join
        with the hook filters in its ON clause. Otherwise the relation gets a nested plan running its query hooks,
        which ``join_strategy`` turns into a LATERAL or CTE join.
        """
        aliased_attribute = self.aliases.aliased_attribute(node)
        relation_filter = node.metadata.data.relation_filter
        node_alias = self.aliases.alias_from_relation_node(node, "target")
        node_select = select(node_alias)
        hooked_select = self.hook_applier.apply_statement_hooks(node_select, node, node_alias)

        if not relation_filter and _is_where_only(hooked_select, node_select):
            hook_where = hooked_select.whereclause
            target = aliased_attribute if hook_where is None else aliased_attribute.and_(hook_where)
            return Join(target, node=node, is_outer=is_outer)

        relationship = node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        target_mapper: Mapper[Any] = relationship.mapper.mapper
        target_alias: AliasedClass[Any] = aliased(target_mapper, flat=True)

        sub_context = replace(
            self,
            aliases=self.aliases.sub(target_mapper.class_, target_alias),
            statement=None,
            default_order_by=(),
        )
        query_graph = QueryGraph(
            sub_context.aliases, order_by=relation_filter.order_by, distinct_on=list(relation_filter.distinct_on)
        )
        plan = plan_query(query_graph, sub_context, limit=relation_filter.limit, offset=relation_filter.offset)
        hook_order_by = self.hook_applier.order_by(node, target_alias)
        plan = replace(
            plan,
            order_by=(*hook_order_by, *plan.order_by),
            hook_specs=(HookSpec(node=node, alias=target_alias, loading_mode="add", export_order_by=True),),
        )
        selection = self.aliases.inspect(node).selection(target_alias)
        selected_keys = {attribute.key for attribute in selection}
        selection.extend(
            sub_context.aliases.aliased_attribute(order_node, target_alias)
            for order_node in query_graph.order_by_nodes
            if order_node.level == 1 and order_node.value.model_field_name not in selected_keys
        )
        join = self.join_strategy.relation_join(
            self.aliases, node, target_alias, plan, selection=selection, is_outer=is_outer
        )
        join.order_nodes = query_graph.order_by_nodes
        adapter = ClauseAdapter(join.selectable)
        join.hook_order_by = tuple(adapter.traverse(clause) for clause in hook_order_by)
        return join


@dataclass(frozen=True)
class AggregationPlan:
    """Aggregation joins and the columns holding each aggregate function's result."""

    columns: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Function node -> its result column, read from the aggregation join."""
    joins: tuple[AggregationJoin, ...] = ()
    """LATERAL or CTE joins computing the aggregates."""
    aliases: Mapping[QueryNodeType, AliasedClass[Any]] = field(default_factory=dict)
    """Aggregation node -> the alias its functions are built against."""
    node_functions: Mapping[QueryNodeType, tuple[QueryNodeType, ...]] = field(default_factory=dict)
    """Aggregation node -> its function nodes, in a stable order."""
    selection_functions: Mapping[QueryNodeType, frozenset[QueryNodeType]] = field(default_factory=dict)
    """Aggregation node -> the function nodes the client selected."""

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        available_columns: Mapping[QueryNodeType, ColumnElement[Any]] | None = None,
    ) -> Self:
        """Builds the aggregation joins and function columns.

        Functions found in ``available_columns`` are read from there, and an aggregation node whose functions are all
        available gets no join.
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
        """Collects one AggregationSpec per aggregation node used by the filter, the ordering or the selection.

        Each function is kept once per node; those reached from the selection are marked as selected.
        """
        aliases = context.aliases
        specs: dict[QueryNodeType, AggregationSpec] = {}

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
        """Builds a LATERAL join computing ``function_columns``, built against ``alias``, for each parent row."""
        root_relation = context.aliases.aliased_attribute(node).of_type(inspect(alias))
        lateral_statement = correlate_relation(select(*function_columns), root_relation, alias).lateral()
        return AggregationJoin(target=lateral_statement, onclause=true(), node=node)

    @staticmethod
    def _cte_join(node: QueryNodeType, alias: Any, statement: Any, context: PlanContext[Any]) -> AggregationJoin:
        """Builds a CTE join running ``statement``, the aggregates select, grouped by the foreign keys to the parent."""
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
        """Builds a CTE join computing the aggregates of a relationship that goes through a secondary table.

        The CTE joins from its own copy of the parent, so SQLAlchemy writes the full ``primaryjoin`` and
        ``secondaryjoin`` conditions, and groups by the parent keys to join back to the query. It is an outer join
        because a parent without related rows has no group.
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
        """Returns the function columns the client selected for an aggregation node, in a stable order."""
        selected = self.selection_functions[node]
        return [self.columns[fn] for fn in self.node_functions[node] if fn in selected]

    def join_for(self, node: QueryNodeType) -> AggregationJoin | None:
        """Returns the join computing an aggregation node, if any."""
        for candidate in self.joins:
            if candidate.node is node:
                return candidate
        return None

    def upsert(self, node: QueryNodeType, emitted: set[QueryNodeType]) -> tuple[list[ColumnElement[Any]], Join | None]:
        """Returns the selected function columns of ``node``, and its join if ``node`` is not yet in ``emitted``.

        Adds ``node`` to ``emitted``.
        """
        function_columns = self.selected_columns_for(node)
        new_join: Join | None = None
        if node not in emitted:
            emitted.add(node)
            new_join = self.join_for(node)
        return function_columns, new_join


@dataclass(frozen=True)
class FilterPlan:
    """WHERE predicates and the relation joins they need."""

    where: tuple[ColumnElement[bool], ...] = ()
    joins: tuple[Join, ...] = ()

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        allow_null: bool = False,
    ) -> Self:
        """Builds the WHERE predicates and the relation joins they need."""
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
        """Converts a filter comparison to SQL predicates, comparing ``override`` instead of the field if given."""
        attribute = override if override is not None else context.aliases.aliased_attribute(dto_filter.field_node)
        expressions: list[ColumnElement[bool]] = dto_filter.to_expressions(context.dialect, attribute)
        if not_null_check:
            expressions.append(attribute.is_not(null()))
        return expressions

    @staticmethod
    def _custom_filter_expression(custom: CustomFilter, context: PlanContext[Any]) -> ColumnElement[bool]:
        """Turns a custom filter into one predicate: a primary-key ``IN`` or a correlated ``EXISTS``.

        The user callback edits a separate ``select(model)``. Matching its primary keys to the outer query's keeps
        the result usable under AND, OR and NOT.
        """
        model = custom.field_node.value.model
        mapper = class_mapper(model)
        inner_pks = SQLAlchemyInspector.pk_attributes(mapper)
        outer_pks = context.aliases.aliased_id_attributes(custom.field_node)

        isolated = custom.apply(select(model), custom.value, dialect=context.dialect, model=model)

        if custom.join == "in":
            inner_select = isolated.with_only_columns(*inner_pks)
            if len(outer_pks) == 1:
                # A plain IN is better supported and optimized than a one-element tuple IN.
                return outer_pks[0].in_(inner_select)
            return tuple_(*outer_pks).in_(inner_select)

        outer_alias = (
            context.aliases.root_alias
            if custom.field_node.is_root
            else context.aliases.alias_from_relation_node(custom.field_node, "target")
        )

        # The outer query aliases the root model with its table name. An inner alias with that same name would
        # compare the table's keys to themselves and match every outer row, so SQLAlchemy picks a unique name.
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
        """Builds the predicates of an aggregation filter.

        Returns:
            The aggregation join if its node is not yet in ``emitted_agg_joins`` (``None`` otherwise), and the
            predicates.
        """
        aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
        alias = agg_plan.aliases[aggregation_node]
        function_node, _ = context.aliases.inspect(aggregation.field_node).filter_function(
            alias, distinct=aggregation.distinct
        )
        function_column = agg_plan.columns[function_node]
        bool_expressions = aggregation.predicate.to_expressions(context.dialect, function_column)

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
        """Builds the predicates and joins of each filter in ``query``."""
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
        """Builds the predicates and joins of a filter's AND, OR and NOT branches."""
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
        """Builds the WHERE predicates of a filter and every join they need."""
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
    """ORDER BY expressions and the relation joins they need."""

    expressions: tuple[UnaryExpression[Any], ...] = ()
    joins: tuple[Join, ...] = ()

    @classmethod
    def plan(
        cls,
        query_graph: QueryGraph[Any],
        context: PlanContext[Any],
        agg_plan: AggregationPlan,
        existing_joins: Sequence[Join],
    ) -> Self:
        """Builds the ORDER BY expressions and the joins they need.

        When the client asks for no ordering, uses ``default_order_by`` and, with ``deterministic_ordering``, the
        primary keys. The own ordering of each join in ``existing_joins`` is appended.
        """
        _default_order_by = list(context.default_order_by)
        relation_expressions = cls._relation_order_by(query_graph, context, existing_joins)

        if not (query_graph.order_by_tree or context.deterministic_ordering or _default_order_by):
            return cls(expressions=tuple(relation_expressions))

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
        return cls(expressions=(*order_by.expressions, *relation_expressions), joins=tuple(order_by.joins))

    @staticmethod
    def _default_order_columns(
        context: PlanContext[Any],
    ) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
        """Resolves ``default_order_by`` against the root alias.

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
        """Appends the ORDER BY column of one node to ``columns``, and the aggregation join it needs to ``joins``.

        Raises:
            TranspilingError: If the node has no order direction.
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
    ) -> list[UnaryExpression[Any]]:
        """Returns the ORDER BY expressions of the selected relation joins.

        Uses each join's hook ordering, then its own ordering or, with ``deterministic_ordering``, its primary keys.
        """
        aliases = context.aliases
        deterministic_ordering = context.deterministic_ordering
        selected_tree = query_graph.resolved_selection_tree()
        expressions: list[UnaryExpression[Any]] = []
        for join in sorted(joins):
            if (
                isinstance(join, AggregationJoin)
                or join.node in query_graph.order_by_nodes
                or not selected_tree.find_child(
                    lambda node, _join=join: node.value.model_field is _join.node.value.model_field
                )
            ):
                continue
            order_by_spec: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
            if not join.order_nodes and deterministic_ordering:
                order_by_spec = [(attribute, OrderByEnum.ASC) for attribute in aliases.aliased_id_attributes(join.node)]
            elif join.order_nodes:
                order_by_spec = [
                    (aliases.scoped_column(join.selectable, node.value.model_field_name), node.metadata.data.order_by)
                    for node in join.order_nodes
                    if node.metadata.data.order_by
                ]
            expressions.extend([*join.hook_order_by, *OrderBy(context.db_features, order_by_spec).expressions])
        return expressions


@dataclass(frozen=True)
class ProjectionPlan:
    """Selected columns, ORM load options, aggregation joins and query hook positions."""

    columns: tuple[ColumnElement[Any], ...] = ()
    load_options: tuple[_AbstractLoad, ...] = ()
    aggregation_joins: tuple[Join, ...] = ()
    hook_specs: tuple[HookSpec, ...] = ()
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Transform node -> its labelled column, for the executor's column map."""
    identity_map: Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]] = field(default_factory=dict)
    """Related level owning computed values -> its primary-key columns."""

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any], agg_plan: AggregationPlan) -> Self:
        """Builds the projection of the selection tree."""
        selection_tree = query_graph.resolved_selection_tree()

        root_columns, column_transforms = context.aliases.inspect(selection_tree).columns()
        projection_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
        transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
            transform.node: transform.attribute for transform in column_transforms
        }
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
            transform_map.update(child_load.transform_map)

        identity_map = cls._identity_columns(selection_tree, context)
        for identity_columns in identity_map.values():
            projection_columns.extend(identity_columns)

        return cls(
            columns=tuple(projection_columns),
            load_options=tuple(load_options),
            aggregation_joins=tuple(aggregation_joins),
            hook_specs=(HookSpec(node=selection_tree.root, alias=context.aliases.root_alias, loading_mode="undefer"),),
            transform_map=transform_map,
            identity_map=identity_map,
        )

    @staticmethod
    def _identity_columns(
        selection_tree: QueryNodeType, context: PlanContext[Any]
    ) -> dict[QueryNodeType, tuple[ColumnElement[Any], ...]]:
        """Selects the primary keys of every related level that owns computed values.

        A result row carries a computed value of one related object, not of the root. Selecting that object's
        primary key lets the executor attach the value to the right object.
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
        """Builds the projection of one selected relation and of its selected sub-relations."""
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

        for child in node.children:
            if not child.value.is_relation or child.value.is_computed:
                continue
            child_load = ProjectionPlan._collect_child_load(child, context)
            transform_columns.extend(child_load.transform_columns)
            load = load.options(child_load.load)
            transform_map.update(child_load.transform_map)

        return ChildLoad(transform_columns=tuple(transform_columns), load=load, transform_map=transform_map)


@dataclass(frozen=True)
class ChildLoad:
    """Projection of one selected relation and of its sub-relations."""

    load: _AbstractLoad
    """``contains_eager`` option loading the relation."""
    transform_columns: tuple[ColumnElement[Any], ...] = ()
    """Transform columns of the subtree, in selection order."""
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]] = field(default_factory=dict)
    """Transform node -> its labelled column."""


@dataclass(frozen=True)
class FilterPhase:
    """Aggregation plan, filter plan and subquery-tree joins, shared by ``plan_query`` and ``_plan_subquery``."""

    agg_plan: AggregationPlan
    filter_plan: FilterPlan
    subquery_tree_joins: tuple[Join, ...] = ()
    """Joins of the subquery tree that the filter does not already make."""

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any], allow_null: bool) -> Self:
        """Builds the aggregation plan, the filter plan and the subquery-tree joins.

        Joins made for the filter run no query hook: hooks restrict the selected rows, not those the filter tests.
        """
        aggregation_plan = AggregationPlan.plan(query_graph, context)
        context = replace(context, hook_applier=context.hook_applier.without(query_graph.filter_relation_nodes))
        filter_plan = FilterPlan.plan(query_graph, context, aggregation_plan, allow_null)
        filter_join_nodes = {join.node for join in filter_plan.joins}
        subquery_tree_joins: list[Join] = []
        if query_graph.subquery_join_tree:
            subquery_tree_joins = [
                join
                for join in _plan_relation_joins(
                    query_graph, context, is_outer=True, tree=query_graph.subquery_join_tree
                )
                if join.node not in filter_join_nodes
            ]
        return cls(agg_plan=aggregation_plan, filter_plan=filter_plan, subquery_tree_joins=tuple(subquery_tree_joins))


@dataclass(frozen=True)
class ProjectionPhase:
    """Root aggregation columns and projection plan, shared by ``plan_query`` and ``_plan_subquery``."""

    root_aggregations_map: Mapping[QueryNodeType, Label[Any]]
    """Root aggregation node -> its window function column."""
    projection_plan: ProjectionPlan

    @classmethod
    def plan(cls, query_graph: QueryGraph[Any], context: PlanContext[Any], agg_plan: AggregationPlan) -> Self:
        """Builds the root aggregation window columns and the projection plan."""
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
        return cls(root_aggregations_map=root_aggregations_map, projection_plan=projection_plan)


@dataclass(frozen=True)
class UserStatementPlan:
    """Applies the user filter statement to the query.

    A statement that only adds WHERE clauses to ``select(model)`` has its WHERE copied into the query. Any other
    statement is joined to the query on the primary key.
    """

    statement: Select[Any]
    aliases: AliasContext[Any]

    def is_trivial(self) -> bool:
        """Tells whether the statement is ``select(model)`` with WHERE clauses only.

        Any other clause, such as a join, GROUP BY or LIMIT, makes it non-trivial. Copying the WHERE of a trivial
        statement drops its ``execution_options``.
        """
        return _is_where_only(self.statement, select(self.aliases.model))

    def inline_where(self, alias: AliasedClass[Any]) -> ColumnElement[bool] | None:
        """Rewrites the statement's WHERE clause to use ``alias`` instead of the model's table."""
        where = self.statement.whereclause
        if where is None:
            return None
        adapter = ClauseAdapter(inspect(alias).selectable)
        return adapter.traverse(where)

    def semijoin(self) -> FilterSemiJoin:
        """Builds the primary-key join from the root alias to the statement."""
        root_mapper = class_mapper(self.aliases.model)
        pk_attributes = SQLAlchemyInspector.pk_attributes(root_mapper)
        filter_alias = cast("Alias", self.statement.with_only_columns(*pk_attributes).subquery().alias())
        on_clause = and_(
            *[getattr(self.aliases.root_alias, attr.key) == filter_alias.c[attr.key] for attr in pk_attributes]
        )
        return FilterSemiJoin(alias=filter_alias, onclause=on_clause)

    def apply_to_statement(self, statement: Select[Any], alias: AliasedClass[Any]) -> Select[Any]:
        """Applies the user statement to ``statement``, copying its WHERE onto ``alias`` or joining it."""
        if not self.is_trivial():
            semijoin = self.semijoin()
            return statement.join(semijoin.alias, onclause=semijoin.onclause)
        where = self.inline_where(alias)
        return statement.where(where) if where is not None else statement


def _is_where_only(statement: Select[Any], base: Select[Any]) -> bool:
    """Tells whether ``statement`` is ``base`` with WHERE clauses only."""
    where = statement.whereclause
    expected = base if where is None else base.where(where)
    try:
        return statement.compare(expected)
    except AttributeError:  # uncomparable statement → not a WHERE-only edit
        return False


def _plan_relation_joins(
    query_graph: QueryGraph[Any], context: PlanContext[Any], is_outer: bool = True, tree: QueryNodeType | None = None
) -> tuple[Join, ...]:
    """Builds a join for every non-computed relation in ``tree``, or in the root join tree, breadth-first."""
    source_tree = tree if tree is not None else query_graph.root_join_tree
    joins: list[Join] = [
        context.build_join(child, is_outer)
        for child in source_tree.iter_breadth_first()
        if not child.value.is_computed and child.value.is_relation and not child.is_root
    ]
    return tuple(joins)


def _use_distinct_rank(query_graph: QueryGraph[Any], context: PlanContext[Any]) -> bool:
    """Tells whether DISTINCT ON must be emulated with a ``row_number()`` window.

    Always the case when the database lacks DISTINCT ON. Otherwise only when the query is ordered and the DISTINCT ON
    fields are not the first ORDER BY columns, which native DISTINCT ON requires.
    """
    if not context.db_features.supports_distinct_on:
        return bool(query_graph.distinct_on)
    if not query_graph.distinct_on:
        return False
    has_ordering = bool(query_graph.order_by_tree or context.deterministic_ordering or context.default_order_by)
    if not has_ordering:
        return False
    distinct_fields = [enum.field_definition for enum in query_graph.distinct_on]
    order_nodes = query_graph.order_by_nodes
    if len(order_nodes) < len(distinct_fields):
        return True
    is_order_prefix = all(
        order_nodes[index].value.model_field is field.model_field for index, field in enumerate(distinct_fields)
    )
    return not is_order_prefix


def _dedup_agg_joins(joins: list[Join]) -> list[Join]:
    """Keeps the first aggregation join of each node and drops the others; other joins are kept."""
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
    """Unwraps an ORM attribute into its column.

    Two attributes for the same column, reached in different ways such as ``getattr(alias, key)`` and
    ``field.adapt_to_entity(insp)``, do not compare equal; their columns do.
    """
    if hasattr(column, "__clause_element__"):
        return column.__clause_element__()
    return column


def _dedup_columns(columns: Sequence[ColumnElement[Any]]) -> list[ColumnElement[Any]]:
    """Removes the columns equal to an earlier one.

    The subquery collects columns from the selection, the ordering and the root aggregations. The same column reached
    twice is a different object, which SQLAlchemy would select twice (``id`` and ``id__1``).
    """
    unique: list[ColumnElement[Any]] = []
    for column in columns:
        col_elem = _clause_element(column)
        if not any(same_column(col_elem, _clause_element(seen)) for seen in unique):
            unique.append(column)
    return unique


def _referenced_function_nodes(agg_plan: AggregationPlan, inner_joins: Sequence[Join]) -> list[QueryNodeType]:
    """Lists the aggregate functions the subquery computes and the outer query reads from it.

    An aggregation node joined in the subquery has all its functions read from there, so the outer query does not
    compute them again. A node the subquery does not join stays in the outer query, computed over the page only.
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
) -> Select[Any]:
    """Builds the SELECT of the pagination or DISTINCT ON subquery, from ``inner_alias``.

    Without ``use_distinct_on``, DISTINCT ON is emulated with a ``row_number()`` rank, filtered before pagination.
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
    projected: list[Any] = _dedup_columns([*only_columns, *selected_function_columns])

    rank_label: KeyedColumnElement[Any] | None = None
    if distinct_on and not use_distinct_on:
        rank_label = (
            func.row_number()
            .over(partition_by=distinct_on.expressions, order_by=list(order_expressions) or None)
            .label(None)
        )
        projected.append(rank_label)

    inner_statement = select(inspect(inner_alias)).options(raiseload("*")).with_only_columns(*projected)
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
        inner_statement = add_missing_columns(inner_statement, [e.element for e in order_expressions])
        inner_statement = inner_statement.distinct(*distinct_on.expressions)
    inner_statement, _ = context.hook_applier.apply(
        inner_statement,
        node=query_graph.root_join_tree.root,
        alias=context.aliases.root_alias,
        loading_mode="add",
        in_subquery=True,
    )
    if rank_label is not None:
        inner_statement = _first_ranked_rows(inner_statement, rank_label, order_expressions)
    if limit is not None:
        inner_statement = inner_statement.limit(limit)
    if offset is not None:
        inner_statement = inner_statement.offset(offset)
    return inner_statement


def _first_ranked_rows(
    statement: Select[Any], rank: KeyedColumnElement[Any], order_expressions: Sequence[UnaryExpression[Any]]
) -> Select[Any]:
    """Keeps the rows of ``statement`` ranked first, ordered by ``order_expressions``."""
    ranked = add_missing_columns(statement, [expression.element for expression in order_expressions]).subquery()
    ranked_rank = require_corresponding_column(ranked, rank)
    adapter = ClauseAdapter(ranked)
    return (
        select(*[column for column in ranked.c if column is not ranked_rank])
        .where(ranked_rank == 1)
        .order_by(*[adapter.traverse(expression) for expression in order_expressions])
    )


def _plan_subquery(
    query_graph: QueryGraph[Any],
    context: PlanContext[Any],
    *,
    limit: int | None,
    offset: int | None,
    allow_null: bool,
    distinct_on_rank: bool,
) -> QueryPlan:
    """Plans a root query whose pagination or DISTINCT ON runs in a subquery.

    The subquery filters, orders and paginates the root rows. The outer query selects from it, joins the relations,
    and reads the aggregates the subquery already computed.
    """
    model = context.aliases.model
    name = model.__tablename__

    # Every inner pass, ``build_join`` included, reads the root alias from ``context.aliases``.
    inner_alias = aliased(class_mapper(model), name=name, flat=True)
    context.aliases.replace(alias=inner_alias)

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    phase = FilterPhase.plan(query_graph, context, allow_null)
    aggregation_plan, filter_plan = phase.agg_plan, phase.filter_plan
    subquery_tree_joins = list(phase.subquery_tree_joins)

    inner_order = OrderPlan.plan(query_graph, context, aggregation_plan, [*filter_plan.joins, *subquery_tree_joins])

    inner_joins = _dedup_agg_joins([*filter_plan.joins, *inner_order.joins, *subquery_tree_joins])
    referenced_functions = _referenced_function_nodes(aggregation_plan, inner_joins)
    selected_function_labels = {fn: aggregation_plan.columns[fn] for fn in referenced_functions}
    inner_statement = _assemble_inner_statement(
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

    context.aliases.replace(alias=outer_alias)

    # Inner aggregation joins reference ``inner_alias``; reusing one would add it to the outer FROM.
    reprojected_agg_columns: dict[QueryNodeType, ColumnElement[Any]] = {
        fn: require_corresponding_column(subquery, cast("KeyedColumnElement[Any]", selected_function_labels[fn]))
        for fn in referenced_functions
    }
    outer_agg_plan = AggregationPlan.plan(query_graph, context, reprojected_agg_columns)

    outer_joins = list(_plan_relation_joins(query_graph, context, is_outer=True))
    outer_order = OrderPlan.plan(query_graph, context, outer_agg_plan, outer_joins)
    outer_joins.extend(outer_order.joins)

    projection_phase = ProjectionPhase.plan(query_graph, context, outer_agg_plan)
    root_agg_map = projection_phase.root_aggregations_map
    root_aggs = tuple(root_agg_map.values())
    outer_proj = projection_phase.projection_plan
    outer_joins.extend(outer_proj.aggregation_joins)

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
        where=(),
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
    """Plans ``query_graph`` into one ``QueryPlan``.

    A root query that is paginated, needs DISTINCT ON emulation, or filters on a relation with query hooks, is
    planned by ``_plan_subquery``: the filter joins such a relation without its hooks, so the selection cannot reuse
    that join.
    """
    distinct_on_rank = _use_distinct_rank(query_graph, context)
    filters_hooked_relation = any(context.hook_applier.has_hooks(node) for node in query_graph.filter_relation_nodes)

    subquery_needed = context.aliases.is_root and (
        limit is not None or offset is not None or distinct_on_rank or filters_hooked_relation
    )
    if subquery_needed:
        return _plan_subquery(
            query_graph, context, limit=limit, offset=offset, allow_null=allow_null, distinct_on_rank=distinct_on_rank
        )

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    phase = FilterPhase.plan(query_graph, context, allow_null)
    aggregation_plan, filter_plan = phase.agg_plan, phase.filter_plan
    subquery_tree_joins = list(phase.subquery_tree_joins)
    subquery_join_nodes = {join.node for join in [*filter_plan.joins, *subquery_tree_joins]}

    root_tree_joins: list[Join] = [
        join
        for join in _plan_relation_joins(query_graph, context, is_outer=True)
        if join.node not in subquery_join_nodes
    ]

    all_relation_joins: list[Join] = [*filter_plan.joins, *subquery_tree_joins, *root_tree_joins]

    order = OrderPlan.plan(query_graph, context, aggregation_plan, all_relation_joins)

    projection_phase = ProjectionPhase.plan(query_graph, context, aggregation_plan)
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
