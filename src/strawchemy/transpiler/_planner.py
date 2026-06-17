"""Pure planner: transforms a QueryGraph into a QueryPlan via pure, composable passes.

This module defines the frozen result dataclasses produced by each planning pass.
The planner replaces the imperative ``_build_query`` / ``Query`` / ``collector`` /
``scope.replace`` machinery with a pipeline of pure functions:

    QueryGraph -> AggregationPlan -> FilterPass + OrderPass + ProjectionPass -> QueryPlan

Each pass returns an immutable result dataclass; no mutable state is threaded between
them.  The emitter (``emit_plan``) is the only place where SQLAlchemy statements are
assembled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, func, inspect, not_, null, or_, select, true
from sqlalchemy.orm import aliased, class_mapper, contains_eager, load_only, raiseload

from strawchemy.constants import AGGREGATIONS_KEY
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.dto.strawberry import AggregationFilter, Filter, OrderByEnum, QueryNode, decompose_order_by
from strawchemy.exceptions import StrawchemyFieldError, TranspilingError
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._plan import FilterSemiJoin, HookSpec, QueryPlan
from strawchemy.transpiler._query import AggregationJoin, AggregationSpec, Conjunction, DistinctOn, OrderBy, Where
from strawchemy.transpiler._scope import require_corresponding_column

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from sqlalchemy import Label, Select
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql.elements import KeyedColumnElement, UnaryExpression
    from sqlalchemy.sql.selectable import Alias

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler._query import Join, QueryGraph
    from strawchemy.transpiler._scope import AliasContext
    from strawchemy.typing import OrderByExpr, QueryNodeType

__all__ = (
    "AggregationPlan",
    "FilterPlan",
    "OrderPlan",
    "ProjectionPlan",
    "plan_aggregations",
    "plan_filter",
    "plan_order",
    "plan_projection",
    "plan_query",
    "plan_relation_joins",
    "plan_root_aggregations",
)


@dataclass(frozen=True)
class AggregationPlan:
    """Aggregation joins and their function-column references, built once and threaded into passes.

    Replaces the mutable ``scope.collector`` aggregation state.
    """

    columns: Mapping[QueryNodeType, ColumnElement[Any]]
    """Function node -> its built aggregation column (corresponded onto the join selectable)."""
    joins: tuple[AggregationJoin, ...]
    """The aggregation lateral/CTE joins, built once."""
    aliases: Mapping[QueryNodeType, AliasedClass[Any]]
    """Aggregation node -> its adaptation alias (spec.alias), needed by filter_function."""
    node_functions: Mapping[QueryNodeType, tuple[QueryNodeType, ...]]
    """Aggregation node -> ordered tuple of its function-node keys (mirrors ``spec.functions`` key order)."""


@dataclass(frozen=True)
class FilterPlan:
    """WHERE predicates and the relation joins they require."""

    where: tuple[ColumnElement[bool], ...]
    joins: tuple[Join, ...]
    referenced_functions: frozenset[QueryNodeType]
    """Function nodes referenced in WHERE predicates (for subquery hoist)."""


@dataclass(frozen=True)
class OrderPlan:
    """Built ORDER BY expressions and the relation joins they require."""

    expressions: tuple[UnaryExpression[Any], ...]
    joins: tuple[Join, ...]
    referenced_functions: frozenset[QueryNodeType]
    """Function nodes referenced in ORDER BY (for subquery hoist)."""


@dataclass(frozen=True)
class ProjectionPlan:
    """Projection columns, ORM load options, selection aggregation joins, and hook specs."""

    columns: tuple[ColumnElement[Any], ...]
    load_options: tuple[_AbstractLoad, ...]
    aggregation_joins: tuple[Join, ...]
    hook_specs: tuple[HookSpec, ...]
    referenced_functions: frozenset[QueryNodeType]
    """Function nodes referenced in the projection selection (for subquery hoist)."""
    transform_map: Mapping[QueryNodeType, ColumnElement[Any]]
    """Maps each transform node to its labelled projection column (for column_map)."""


def _iter_aggregation_filters(query_filter: Filter) -> Iterable[AggregationFilter]:
    """Yields every AggregationFilter in a filter tree in traversal order.

    Args:
        query_filter: The processed filter to walk.

    Yields:
        Each aggregation filter found under the AND, OR and NOT branches.
    """
    for value in query_filter.and_:
        if isinstance(value, AggregationFilter):
            yield value
        elif isinstance(value, Filter):
            yield from _iter_aggregation_filters(value)
    for value in query_filter.or_:
        yield from _iter_aggregation_filters(value)
    if query_filter.not_ is not None:
        yield from _iter_aggregation_filters(query_filter.not_)


def _aggregation_lateral_join(
    node: QueryNodeType, function_columns: Iterable[ColumnElement[Any]], alias: Any, ctx: AliasContext[Any]
) -> AggregationJoin:
    """Creates a lateral aggregation join for a query node.

    Args:
        node: The aggregation node.
        function_columns: The aggregate function columns to include in the lateral.
        alias: The aliased target class the function expressions are adapted to.
        ctx: The query scope providing inspect/aliased_attribute.

    Returns:
        An AggregationJoin backed by a lateral subquery.
    """
    root_relation = ctx.aliased_attribute(node).of_type(inspect(alias))
    lateral_statement = select(*function_columns).where(root_relation).lateral()
    return AggregationJoin(target=lateral_statement, onclause=true(), node=node)


def _aggregation_cte_join(node: QueryNodeType, alias: Any, statement: Any, ctx: AliasContext[Any]) -> AggregationJoin:
    """Creates a CTE-based aggregation join for a query node.

    Args:
        node: The aggregation node.
        alias: The aliased target class for the aggregation target.
        statement: The SQLAlchemy select statement selecting the aggregate functions.
        ctx: The query scope providing inspect for FK resolution.

    Returns:
        An AggregationJoin backed by a CTE.
    """
    remote_fks = ctx.inspect(node).foreign_key_columns("target", alias)
    cte_statement = (
        statement.add_columns(*remote_fks)
        .group_by(*remote_fks)
        .where(and_(*[fk.is_not(null()) for fk in remote_fks]))
        .cte()
    )
    cte_alias = aliased(alias, cte_statement)
    return AggregationJoin(target=cte_alias, onclause=ctx.aliased_attribute(node).of_type(cte_alias), node=node)


def _accumulate_aggregation_specs(
    query_graph: QueryGraph[Any], ctx: AliasContext[Any]
) -> dict[QueryNodeType, AggregationSpec]:
    """Accumulates one AggregationSpec per aggregation node from the query graph.

    Visits sources in fixed order — filter, order-by, selection — and deduplicates
    function expressions per aggregation node by their function_node key.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope used for node inspection and alias creation.

    Returns:
        An ordered mapping of aggregation node to its accumulated spec.
    """
    specs: dict[QueryNodeType, AggregationSpec] = {}

    # Filter source
    if query_graph.query_filter is not None:
        for aggregation in _iter_aggregation_filters(query_graph.query_filter):
            aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
            spec = specs.get(aggregation_node)
            if spec is None:
                spec = specs[aggregation_node] = AggregationSpec.create(aggregation_node, ctx)
            function_node, function = ctx.inspect(aggregation.field_node).filter_function(
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
            spec = specs[aggregation_node] = AggregationSpec.create(aggregation_node, ctx)
        for child_inspect in ctx.inspect(aggregation_node).children:
            for function_node, function in child_inspect.output_functions(spec.alias).items():
                if function_node not in spec.functions:
                    spec.functions[function_node] = function

    return specs


def plan_aggregations(
    query_graph: QueryGraph[Any], ctx: AliasContext[Any], db_features: DatabaseFeatures
) -> AggregationPlan:
    """Builds aggregation joins and function-column references purely, without mutating scope.

    Reproduces the logic of ``QueryTranspiler._aggregation_specs`` and
    ``_build_aggregation_joins`` as a single pure function.  Sources are visited in
    the same fixed order — filter, then order-by, then selection — with the same
    dedup-by-function_node semantics.  No ``collector`` mutations occur; the resolved
    column labels and the built joins are returned as an immutable ``AggregationPlan``.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope used for node inspection, alias resolution, and column
            scoping.  Only read-only methods are called (``inspect``, ``key``,
            ``scoped_column``, ``aliased_attribute``).
        db_features: Database-capability flags.  Used to decide between a lateral
            join and a CTE join (``db_features.supports_lateral``).  This cannot be
            derived from ``ctx`` because ``AliasContext._inspector`` is a base
            ``SQLAlchemyInspector`` that does not carry ``db_features``; only the
            ``SQLAlchemyGraphQLInspector`` held by ``QueryTranspiler`` does.

    Returns:
        An ``AggregationPlan`` whose ``columns`` mapping provides
        ``{function_node: labelled_column}`` for every function referenced across
        all aggregation specs, whose ``joins`` tuple contains one
        ``AggregationJoin`` per spec that has at least one function (same ordering
        and filtering as the legacy ``_build_aggregation_joins``), and whose
        ``aliases`` mapping provides ``{aggregation_node: spec.alias}`` so that
        ``plan_filter`` can call ``filter_function`` with the correct adaptation alias.
    """
    specs = _accumulate_aggregation_specs(query_graph, ctx)
    columns: dict[QueryNodeType, ColumnElement[Any]] = {}
    aliases: dict[QueryNodeType, AliasedClass[Any]] = {}
    node_functions: dict[QueryNodeType, tuple[QueryNodeType, ...]] = {}
    joins: list[AggregationJoin] = []

    for aggregation_node, spec in specs.items():
        if not spec.functions:
            continue
        if db_features.supports_lateral:
            join = _aggregation_lateral_join(aggregation_node, spec.functions.values(), spec.alias, ctx)
        else:
            join = _aggregation_cte_join(
                node=aggregation_node, alias=spec.alias, statement=select(*spec.functions.values()), ctx=ctx
            )
        for function_node, inner_label in spec.functions.items():
            columns[function_node] = require_corresponding_column(join.selectable, inner_label)
        aliases[aggregation_node] = spec.alias
        node_functions[aggregation_node] = tuple(spec.functions.keys())
        joins.append(join)

    return AggregationPlan(columns=columns, joins=tuple(joins), aliases=aliases, node_functions=node_functions)


def _filter_to_expressions(
    ctx: AliasContext[Any],
    dto_filter: GraphQLComparison,
    dialect: Any,
    override: ColumnElement[Any] | None = None,
    not_null_check: bool = False,
) -> list[ColumnElement[bool]]:
    """Converts a DTO filter comparison to a list of SQLAlchemy expressions.

    Port of ``QueryTranspiler._filter_to_expressions``.

    Args:
        ctx: The query scope for resolving aliased attributes.
        dto_filter: The DTO filter comparison to convert.
        dialect: The SQLAlchemy dialect for expression building.
        override: An optional column element to override the filter attribute.
        not_null_check: Whether to add a not-null check to the expressions.

    Returns:
        A list of SQLAlchemy boolean expressions.
    """
    attribute = override if override is not None else ctx.aliased_attribute(dto_filter.field_node)
    expressions: list[ColumnElement[bool]] = dto_filter.to_expressions(dialect, attribute)
    if not_null_check:
        expressions.append(attribute.is_not(null()))
    return expressions


def _aggregation_filter_pure(
    aggregation: AggregationFilter,
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    dialect: Any,
    emitted_agg_joins: set[QueryNodeType],
) -> tuple[Join | None, list[ColumnElement[bool]], QueryNodeType]:
    """Looks up an aggregation filter's column and builds its filter expressions.

    Args:
        aggregation: The aggregation filter to process.
        ctx: The query scope for node inspection.
        agg_plan: The pre-built aggregation plan providing columns and aliases.
        dialect: The SQLAlchemy dialect for expression building.
        emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.

    Returns:
        A tuple of:
            - The aggregation join the first time it is needed for this node, ``None`` otherwise.
            - A list of boolean filter expressions.
            - The function_node referenced in this WHERE predicate.
    """
    aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
    alias = agg_plan.aliases[aggregation_node]
    function_node, _ = ctx.inspect(aggregation.field_node).filter_function(alias, distinct=aggregation.distinct)
    function_column = agg_plan.columns[function_node]
    bool_expressions = aggregation.predicate.to_expressions(dialect, function_column)

    # Emit the aggregation join at most once.
    agg_join: Join | None = None
    if aggregation_node not in emitted_agg_joins:
        emitted_agg_joins.add(aggregation_node)
        for candidate in agg_plan.joins:
            if candidate.node is aggregation_node:
                agg_join = candidate
                break

    return agg_join, bool_expressions, function_node


def _gather_conjunctions_pure(
    query: Sequence[Filter | AggregationFilter | GraphQLComparison],
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    dialect: Any,
    emitted_agg_joins: set[QueryNodeType],
    where_function_nodes: set[QueryNodeType],
    join_builder: Callable[[QueryNodeType, bool], Join],
    not_null_check: bool = False,
) -> Conjunction:
    """Gathers all conjunctions from a sequence of filters (pure port).

    Args:
        query: A sequence of filters to gather conjunctions from.
        ctx: The query scope for attribute resolution.
        agg_plan: The pre-built aggregation plan.
        dialect: The SQLAlchemy dialect.
        emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
        where_function_nodes: Mutable set accumulating function nodes in WHERE.
        join_builder: Callable ``(node, is_outer) -> Join`` for relation joins.
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
            agg_join, aggregation_expressions, function_node = _aggregation_filter_pure(
                value, ctx, agg_plan, dialect, emitted_agg_joins
            )
            where_function_nodes.add(function_node)
            if agg_join is not None:
                joins.append(agg_join)
            bool_expressions.extend(aggregation_expressions)
        elif isinstance(value, GraphQLComparison):
            node_path = value.field_node.path_from_root()
            bool_expressions.extend(_filter_to_expressions(ctx, value, dialect, not_null_check=not_null_check))
        else:
            conjunction = _conjunctions_pure(
                value, ctx, agg_plan, dialect, emitted_agg_joins, where_function_nodes, join_builder, not_null_check
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


def _conjunctions_pure(
    query: Filter,
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    dialect: Any,
    emitted_agg_joins: set[QueryNodeType],
    where_function_nodes: set[QueryNodeType],
    join_builder: Callable[[QueryNodeType, bool], Join],
    allow_null: bool = False,
) -> Conjunction:
    """Processes a filter's AND, OR, and NOT conditions into a conjunction (pure port).

    Args:
        query: The filter to process.
        ctx: The query scope.
        agg_plan: The pre-built aggregation plan.
        dialect: The SQLAlchemy dialect.
        emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
        where_function_nodes: Mutable set accumulating function nodes in WHERE.
        join_builder: Callable ``(node, is_outer) -> Join`` for relation joins.
        allow_null: Whether to allow null values in the filter conditions.

    Returns:
        A conjunction of expressions, joins, and common join path.
    """
    bool_expressions: list[ColumnElement[bool]] = []
    and_conjunction = _gather_conjunctions_pure(
        query.and_, ctx, agg_plan, dialect, emitted_agg_joins, where_function_nodes, join_builder, allow_null
    )
    or_conjunction = _gather_conjunctions_pure(
        query.or_, ctx, agg_plan, dialect, emitted_agg_joins, where_function_nodes, join_builder, allow_null
    )
    common_path = QueryNode.common_path(and_conjunction.common_join_path, or_conjunction.common_join_path)
    joins = [*and_conjunction.joins, *or_conjunction.joins]

    if query.not_:
        not_conjunction = _gather_conjunctions_pure(
            [query.not_],
            ctx,
            agg_plan,
            dialect,
            emitted_agg_joins,
            where_function_nodes,
            join_builder,
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


def _where_pure(
    query_filter: Filter,
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    dialect: Any,
    emitted_agg_joins: set[QueryNodeType],
    where_function_nodes: set[QueryNodeType],
    join_builder: Callable[[QueryNodeType, bool], Join],
    allow_null: bool = False,
) -> Where:
    """Creates WHERE expressions and joins from a filter (pure port).

    Args:
        query_filter: The filter to create expressions from.
        ctx: The query scope.
        agg_plan: The pre-built aggregation plan.
        dialect: The SQLAlchemy dialect.
        emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.
        where_function_nodes: Mutable set accumulating function nodes in WHERE.
        join_builder: Callable ``(node, is_outer) -> Join`` for relation joins.
        allow_null: Whether to allow null values in the filter conditions.

    Returns:
        A Where containing expressions and required joins.
    """
    conjunction = _conjunctions_pure(
        query_filter, ctx, agg_plan, dialect, emitted_agg_joins, where_function_nodes, join_builder, allow_null
    )
    return Where(
        conjunction,
        [
            *conjunction.joins,
            *[
                join_builder(node, False)
                for node in conjunction.common_join_path
                if not node.is_root and node.value.is_relation
            ],
        ],
    )


def plan_filter(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    dialect: Any,
    join_builder: Callable[[QueryNodeType, bool], Join],
    allow_null: bool = False,
) -> FilterPlan:
    """Builds the WHERE predicates and their relation joins (pure port).

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope (read-only: inspect, aliased_attribute, etc.).
        agg_plan: The pre-built aggregation plan (columns, joins, aliases).
        dialect: The SQLAlchemy dialect for expression building.
        join_builder: Callable ``(node, is_outer) -> Join`` used to build
            relation joins required by the WHERE common-path, typically the
            transpiler's bound ``_join`` method until Task 5 makes it pure.
        allow_null: Whether to allow null values in filter conditions.

    Returns:
        A FilterPass containing WHERE predicates, required relation/aggregation
        joins, and the set of function nodes referenced in WHERE.
    """
    if not query_graph.query_filter:
        return FilterPlan(where=(), joins=(), referenced_functions=frozenset())

    emitted_agg_joins: set[QueryNodeType] = set()
    where_function_nodes: set[QueryNodeType] = set()

    where = _where_pure(
        query_graph.query_filter,
        ctx,
        agg_plan,
        dialect,
        emitted_agg_joins,
        where_function_nodes,
        join_builder,
        allow_null,
    )
    return FilterPlan(
        where=tuple(where.expressions), joins=tuple(where.joins), referenced_functions=frozenset(where_function_nodes)
    )


def _default_order_columns(
    ctx: AliasContext[Any],
    default_order_by: Sequence[OrderByExpr],
) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
    """Builds ORDER BY columns from the field's default_order_by expressions.

    Pure port of ``QueryTranspiler._default_order_columns``.

    Args:
        ctx: The query scope providing the root alias.
        default_order_by: The declared default order expressions.

    Returns:
        A list of ``(aliased_column, OrderByEnum)`` tuples in declared order.

    Raises:
        StrawchemyFieldError: If an expression references a column not on the root model.
    """
    alias_insp = inspect(ctx.root_alias)
    column_keys = {attr.key for attr in alias_insp.mapper.column_attrs}
    columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
    for expr in default_order_by:
        decomposed = decompose_order_by(expr)
        if decomposed.key not in column_keys:  # pragma: no cover  # defensive
            msg = f"`default_order_by` column '{decomposed.key}' is not a column of {ctx.model.__name__}"
            raise StrawchemyFieldError(msg)
        aliased_attribute = alias_insp.mapper.attrs[decomposed.key].class_attribute.adapt_to_entity(alias_insp)
        columns.append((aliased_attribute, decomposed.order))
    return columns


def _find_agg_join(agg_plan: AggregationPlan, aggregation_node: QueryNodeType) -> AggregationJoin | None:
    """Finds the AggregationJoin for a given aggregation node in the plan.

    Args:
        agg_plan: The pre-built aggregation plan.
        aggregation_node: The aggregation node to look up.

    Returns:
        The matching AggregationJoin, or None if not found.
    """
    for candidate in agg_plan.joins:
        if candidate.node is aggregation_node:
            return candidate
    return None


def _build_order_by_node(
    node: QueryNodeType,
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    seen_aggregation_nodes: set[QueryNodeType],
    emitted_agg_joins: set[QueryNodeType],
    order_by_function_nodes: set[QueryNodeType],
    columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]],
    joins: list[Join],
) -> None:
    """Processes a single order-by node, updating columns/joins/tracked sets in place.

    Extracted from ``plan_order`` to reduce cyclomatic complexity.

    Args:
        node: The order-by node to process.
        ctx: The query scope.
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
            agg_join = _find_agg_join(agg_plan, first_aggregate_parent)
        agg_columns = _aggregation_columns(agg_plan, first_aggregate_parent)
        columns.extend([(col, node.metadata.data.order_by) for col in agg_columns])
        seen_aggregation_nodes.add(first_aggregate_parent)
        if agg_join is not None:
            joins.append(agg_join)
    else:
        columns.append((ctx.aliased_attribute(node), node.metadata.data.order_by))


def plan_order(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    existing_joins: Sequence[Join],
    db_features: DatabaseFeatures,
    default_order_by: Sequence[OrderByExpr] | None = None,
    deterministic_ordering: bool = False,
) -> OrderPlan:
    """Builds the ORDER BY expressions and their relation joins (pure port).

    Port of ``QueryTranspiler._order_by`` + ``_order_pass`` +
    ``_relation_order_by`` + ``_default_order_columns``.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope (read-only: inspect, aliased_attribute, etc.).
        agg_plan: The pre-built aggregation plan providing function columns.
        existing_joins: The relation joins gathered so far (used by
            ``_relation_order_by`` to detect joins that need ordering).
        db_features: Database-capability flags for NULL ordering support.
        default_order_by: Default ordering applied when the client supplies none.
        deterministic_ordering: Whether to append PK tiebreaker columns.

    Returns:
        An OrderPass with ORDER BY expressions, new relation joins required by
        the order columns, and the set of function nodes referenced in ORDER BY.
    """
    _default_order_by = list(default_order_by or [])

    # _order_pass: early-exit when no ordering applies.
    if not (query_graph.order_by_tree or deterministic_ordering or _default_order_by):
        return OrderPlan(expressions=(), joins=(), referenced_functions=frozenset())

    # _order_by: build columns + joins from order_by_nodes.
    columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = []
    joins: list[Join] = []
    order_by_function_nodes: set[QueryNodeType] = set()
    seen_aggregation_nodes: set[QueryNodeType] = set()
    emitted_agg_joins: set[QueryNodeType] = set()

    for node in query_graph.order_by_nodes:
        _build_order_by_node(
            node, ctx, agg_plan, seen_aggregation_nodes, emitted_agg_joins, order_by_function_nodes, columns, joins
        )

    no_user_columns = not columns
    if no_user_columns and _default_order_by:
        columns.extend(_default_order_columns(ctx, _default_order_by))
    if no_user_columns and deterministic_ordering:
        pk_aliases = [
            pk_attribute.adapt_to_entity(inspect(ctx.root_alias))
            for pk_attribute in SQLAlchemyInspector.pk_attributes(ctx.model.__mapper__)
        ]
        columns.extend([(id_col, OrderByEnum.ASC) for id_col in pk_aliases])

    order_by = OrderBy(db_features, columns, joins)

    # _relation_order_by: add ordering for joined relations.
    relation_order_columns = _relation_order_by_pure(query_graph, ctx, existing_joins, deterministic_ordering)
    order_by.columns.extend(relation_order_columns)

    return OrderPlan(
        expressions=tuple(order_by.expressions),
        joins=tuple(order_by.joins),
        referenced_functions=frozenset(order_by_function_nodes),
    )


def _aggregation_columns(agg_plan: AggregationPlan, node: QueryNodeType) -> list[ColumnElement[Any]]:
    """Returns the function columns for an aggregation node in spec order.

    Literal port of ``[collector.columns[fn] for fn in spec.functions]`` from
    ``QueryTranspiler._upsert_aggregations``.  Uses the pre-recorded
    ``node_functions`` key order so column order is byte-identical to the legacy
    path.

    Args:
        agg_plan: The pre-built aggregation plan.
        node: The aggregation node whose function columns are requested.

    Returns:
        A list of labelled function columns for the aggregation node, in
        ``spec.functions`` key order.
    """
    fn_keys = agg_plan.node_functions.get(node)
    if fn_keys is None:
        return []
    return [agg_plan.columns[fn] for fn in fn_keys]


def _relation_order_by_pure(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    joins: Sequence[Join],
    deterministic_ordering: bool,
) -> list[tuple[SQLColumnExpression[Any], OrderByEnum]]:
    """Generates ORDER BY specs for related entities (pure port).

    Port of ``QueryTranspiler._relation_order_by``.

    Args:
        query_graph: The query graph containing selection and ordering information.
        ctx: The query scope for aliased attribute resolution.
        joins: The relation joins gathered so far.
        deterministic_ordering: Whether deterministic PK ordering is enabled.

    Returns:
        A list of ``(column, OrderByEnum)`` tuples for relation ordering.
    """
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
            order_by_spec.extend([(attribute, OrderByEnum.ASC) for attribute in ctx.aliased_id_attributes(join.node)])
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


def plan_relation_joins(
    query_graph: QueryGraph[Any],
    join_builder: Callable[[QueryNodeType, bool], Join],
    is_outer: bool = True,
    tree: QueryNodeType | None = None,
) -> tuple[Join, ...]:
    """Gathers all relation joins needed for a query tree (pure port).

    Port of ``QueryTranspiler._gather_joins``.  The ``join_builder`` parameter
    receives the transpiler's bound ``_join`` method until Task 5 makes
    relation-join construction fully pure.

    Args:
        query_graph: The graph representation of the query being planned.
        join_builder: Callable ``(node, is_outer) -> Join`` that constructs a
            single relation join, typically the transpiler's bound ``_join``.
        is_outer: Whether to create outer joins.
        tree: The tree to gather joins from.  Defaults to
            ``query_graph.root_join_tree`` when ``None``.

    Returns:
        A tuple of Join objects for every non-computed relation child of the
        given tree, in breadth-first traversal order.
    """
    source_tree = tree if tree is not None else query_graph.root_join_tree
    joins: list[Join] = [
        join_builder(child, is_outer)
        for child in source_tree.iter_breadth_first()
        if not child.value.is_computed and child.value.is_relation and not child.is_root
    ]
    return tuple(joins)


def _upsert_aggregations_pure(
    agg_plan: AggregationPlan,
    aggregation_node: QueryNodeType,
    emitted_agg_joins: set[QueryNodeType],
) -> tuple[list[ColumnElement[Any]], Join | None]:
    """Reads columns of an already-built aggregation join, emitting it once (pure port).

    Port of ``QueryTranspiler._upsert_aggregations``.

    Args:
        agg_plan: The pre-built aggregation plan.
        aggregation_node: The aggregation node whose columns are requested.
        emitted_agg_joins: Mutable set tracking already-emitted aggregation joins.

    Returns:
        A tuple of the resolved function columns and the join (emitted at most once).
    """
    function_columns = _aggregation_columns(agg_plan, aggregation_node)
    new_join: Join | None = None
    if aggregation_node not in emitted_agg_joins:
        emitted_agg_joins.add(aggregation_node)
        new_join = _find_agg_join(agg_plan, aggregation_node)
    return function_columns, new_join


def _collect_child_load_pure(
    node: QueryNodeType,
    ctx: AliasContext[Any],
    hook_applier: Any,
) -> tuple[list[ColumnElement[Any]], Any, list[HookSpec], dict[QueryNodeType, ColumnElement[Any]]]:
    """Collects a child relation's transform columns, eager-load option, and hook specs.

    Pure port of ``QueryTranspiler._collect_child_load``.

    Args:
        node: The relation node to collect loads for.
        ctx: The query scope (read-only).
        hook_applier: The HookApplier instance.

    Returns:
        A tuple of (transform columns, the eager-load option, outer hook specs, the
        node->label map for the transform columns of this subtree).
    """
    columns, column_transforms = ctx.inspect(node).columns()
    transform_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
    transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
        transform.node: transform.attribute for transform in column_transforms
    }
    eager_options: list[_AbstractLoad] = [load_only(*columns)] if columns else []
    node_alias = ctx.alias_from_relation_node(node, "target")
    eager_options.extend(hook_applier.collect_load_options(node, node_alias))
    load = contains_eager(ctx.aliased_attribute(node)).options(*eager_options)
    hook_specs: list[HookSpec] = [HookSpec(node=node, alias=node_alias, loading_mode="undefer")]
    for child in node.children:
        if not child.value.is_relation or child.value.is_computed:
            continue
        child_transforms, child_load, child_hook_specs, child_transform_map = _collect_child_load_pure(
            child, ctx, hook_applier
        )
        transform_columns.extend(child_transforms)
        load = load.options(child_load)
        hook_specs.extend(child_hook_specs)
        transform_map.update(child_transform_map)

    return transform_columns, load, hook_specs, transform_map


def plan_projection(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    agg_plan: AggregationPlan,
    hook_applier: Any,
) -> ProjectionPlan:
    """Collects projection columns, ORM load options, aggregation joins, and hook specs.

    Port of ``QueryTranspiler._collect_select`` + ``_collect_child_load``.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope (read-only: inspect, aliased_attribute, etc.).
        agg_plan: The pre-built aggregation plan providing function columns.
        hook_applier: The HookApplier instance for collecting load options.

    Returns:
        A ProjectionPass containing projection columns, load options, aggregation
        joins for the selection (with within-pass emit-once deduplication), hook
        specs, and the set of leaf function nodes referenced in the projection
        selection. Cross-pass deduplication of aggregation joins across
        filter/order/projection is the composer's responsibility (``plan_query``).
    """
    selection_tree = query_graph.resolved_selection_tree()

    root_columns, column_transforms = ctx.inspect(selection_tree).columns()
    projection_columns: list[ColumnElement[Any]] = [transform.attribute for transform in column_transforms]
    transform_map: dict[QueryNodeType, ColumnElement[Any]] = {
        transform.node: transform.attribute for transform in column_transforms
    }
    hook_specs: list[HookSpec] = [HookSpec(node=selection_tree.root, alias=ctx.root_alias, loading_mode="undefer")]
    aggregation_joins: list[Join] = []
    emitted_agg_joins: set[QueryNodeType] = set()

    for node in selection_tree.iter_depth_first():
        if node.value.is_aggregate:
            agg_columns, new_join = _upsert_aggregations_pure(agg_plan, node, emitted_agg_joins)
            projection_columns.extend(agg_columns)
            if new_join is not None:
                aggregation_joins.append(new_join)

    # Mirror legacy QueryGraph.resolved_selection_tree: only leaf function nodes.
    referenced_functions = frozenset(
        node for node in selection_tree.leaves(iteration_mode="breadth_first") if node.value.is_function
    )

    load_options: list[_AbstractLoad] = [load_only(*root_columns)] if root_columns else []
    load_options.extend(hook_applier.collect_load_options(selection_tree.root, ctx.root_alias))
    for child in selection_tree.children:
        if not child.value.is_relation or child.value.is_computed:
            continue
        child_transforms, child_load, child_hook_specs, child_transform_map = _collect_child_load_pure(
            child, ctx, hook_applier
        )
        projection_columns.extend(child_transforms)
        load_options.append(child_load)
        hook_specs.extend(child_hook_specs)
        transform_map.update(child_transform_map)

    return ProjectionPlan(
        columns=tuple(projection_columns),
        load_options=tuple(load_options),
        aggregation_joins=tuple(aggregation_joins),
        hook_specs=tuple(hook_specs),
        referenced_functions=referenced_functions,
        transform_map=transform_map,
    )


def plan_root_aggregations(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
) -> dict[QueryNodeType, Label[Any]]:
    """Builds root aggregation window-function columns (pure port).

    Port of ``QueryTranspiler._root_aggregation_functions``.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope (read-only: inspect, root_alias).

    Returns:
        A mapping of query node to its labelled root aggregation function
        expression, preserving the order in which aggregation children appear,
        or an empty mapping when no root aggregations are present.
    """
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


def _use_distinct_rank_pure(
    query_graph: QueryGraph[Any],
    db_features: DatabaseFeatures,
    deterministic_ordering: bool,
    default_order_by: Sequence[OrderByExpr],
) -> bool:
    """Pure port of ``QueryTranspiler._use_distinct_rank``.

    Args:
        query_graph: The graph representation of the query being planned.
        db_features: Database-capability flags.
        deterministic_ordering: Whether deterministic PK ordering is enabled.
        default_order_by: Default ordering expressions.

    Returns:
        True if RANK() window function should be used for DISTINCT ON, False otherwise.
    """
    if db_features.supports_distinct_on:
        return bool(
            query_graph.distinct_on and (query_graph.order_by_tree or deterministic_ordering or default_order_by)
        )
    return bool(query_graph.distinct_on)


def _build_filter_semijoin_pure(
    ctx: AliasContext[Any],
    statement: Select[Any],
) -> FilterSemiJoin:
    """Pure port of ``QueryTranspiler._build_filter_semijoin``.

    Builds the PK semi-join from the root alias to the filter-statement subquery.

    Args:
        ctx: The query scope providing the root alias and model.
        statement: The base filter Select statement whose PK columns form the subquery.

    Returns:
        A FilterSemiJoin with the subquery alias and the PK-equality onclause.
    """
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


def _referenced_function_nodes(filt: FilterPlan, order: OrderPlan, proj: ProjectionPlan) -> list[QueryNodeType]:
    """Computes the function nodes hoisted into the pagination/distinct subquery.

    Mirrors ``FunctionNodeCollector.referenced``: function nodes appearing in both
    WHERE and the selection, plus every function node used in ORDER BY.  Order is
    deterministic — WHERE∩selection first (in selection traversal order), then the
    remaining ORDER BY nodes — so the columns selected into the subquery and the
    columns re-projected from it agree on membership and order.

    Args:
        filt: The inner filter pass (WHERE function references).
        order: The inner order pass (ORDER BY function references).
        proj: The inner projection pass (selection function references).

    Returns:
        The ordered list of referenced function nodes.
    """
    where_and_selection = filt.referenced_functions & proj.referenced_functions
    referenced: list[QueryNodeType] = [node for node in proj.referenced_functions if node in where_and_selection]
    referenced.extend(node for node in order.referenced_functions if node not in where_and_selection)
    return referenced


def _assemble_inner_statement(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    hook_applier: Any,
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
    statement: Select[Any] | None,
) -> tuple[Select[Any], KeyedColumnElement[Any] | None]:
    """Assembles the inner pagination/distinct subquery SELECT (mirrors SubqueryBuilder.build).

    Selects the root selection columns, order-by columns, root-aggregation argument
    columns and the hoisted aggregation function columns, then applies the optional
    filter semi-join, joins, WHERE, ORDER BY, native DISTINCT ON, and LIMIT/OFFSET,
    finally replaying the in-subquery hooks.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope, currently rooted on ``inner_alias``.
        hook_applier: The HookApplier instance.
        inner_alias: The fresh root alias the subquery selects from.
        distinct_on: The DISTINCT ON configuration for the subquery.
        use_distinct_on: Whether native DISTINCT ON applies (False ⇒ rank emulation).
        inner_joins: The deduplicated inner joins (relation + aggregation).
        where: The inner WHERE predicates.
        order_expressions: The built inner ORDER BY expressions.
        selected_function_columns: The hoisted aggregation function columns.
        limit: Optional pagination limit.
        offset: Optional pagination offset.
        statement: Optional base filter Select statement, joined in as a PK semi-join.

    Returns:
        A tuple of the assembled inner statement and the anonymous rank-column label
        (``None`` when DISTINCT ON is not emulated via a window rank).
    """
    only_columns: list[Any] = [
        *ctx.inspect(query_graph.root_join_tree).selection(inner_alias),
        *[ctx.aliased_attribute(node) for node in query_graph.order_by_nodes if not node.value.is_computed],
    ]
    if aggregation_tree := query_graph.root_aggregation_tree():
        only_columns.extend(
            ctx.aliased_attribute(child) for child in aggregation_tree.leaves() if child.value.is_function_arg
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
    # semi-join, so LIMIT/OFFSET count only those rows (mirrors _apply_filter_statement).
    if statement is not None:
        semijoin = _build_filter_semijoin_pure(ctx, statement)
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
    inner_statement, _ = hook_applier.apply(
        inner_statement,
        node=query_graph.root_join_tree.root,
        alias=ctx.root_alias,
        loading_mode="add",
        in_subquery=True,
    )
    return inner_statement, rank_label


def _plan_subquery(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    db_features: DatabaseFeatures,
    dialect: Any,
    hook_applier: Any,
    join_builder: Callable[[QueryNodeType, bool], Join],
    limit: int | None,
    offset: int | None,
    allow_null: bool,
    default_order_by: Sequence[OrderByExpr],
    deterministic_ordering: bool,
    statement: Select[Any] | None,
    distinct_on_rank: bool,
) -> QueryPlan:
    """Plans the root pagination/distinct-rank subquery boundary.

    Pure port of ``SubqueryBuilder.build`` + ``_subquery_pass`` + the subquery branch
    of ``QueryTranspiler._build_plan``.  The inner statement is assembled selecting from
    a fresh root alias (pagination/distinct happen inside it); the outer query joins the
    materialized subquery and re-projects the hoisted aggregation columns onto it.

    ``ctx`` is re-rooted in place (via ``AliasContext.replace``) onto the inner alias and
    then the subquery alias, so the ``join_builder`` — which closes over ``ctx`` — builds
    joins against the correct root at each phase, exactly as the imperative path did.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The root query scope, re-rooted in place.
        db_features: Database-capability flags.
        dialect: The SQLAlchemy dialect for expression building.
        hook_applier: The HookApplier instance.
        join_builder: Callable ``(node, is_outer) -> Join`` for relation joins.
        limit: Optional pagination limit (consumed inside the subquery).
        offset: Optional pagination offset (consumed inside the subquery).
        allow_null: Whether to allow null values in filter conditions.
        default_order_by: Default ordering applied when the client supplies none.
        deterministic_ordering: Whether to append PK tiebreaker columns.
        statement: Optional base filter Select statement, joined into the subquery.
        distinct_on_rank: Whether DISTINCT ON is emulated via a window rank column.

    Returns:
        The flat outer ``QueryPlan`` selecting from the materialized subquery.
    """
    model = ctx.model
    name = model.__tablename__

    # Phase 0: re-root onto a fresh inner alias so all inner passes and the
    # join_builder (which closes over ctx) build against the subquery's FROM.
    inner_alias = cast("AliasedClass[Any]", aliased(class_mapper(model), name=name, flat=True))
    ctx.replace(alias=inner_alias)

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    # Phase 1: inner passes against the inner alias.
    agg_plan = plan_aggregations(query_graph, ctx, db_features)
    filt = plan_filter(query_graph, ctx, agg_plan, dialect, join_builder, allow_null)
    subquery_join_nodes: set[QueryNodeType] = {j.node for j in filt.joins}

    subquery_tree_joins: list[Join] = []
    if query_graph.subquery_join_tree:
        subquery_tree_joins = [
            j
            for j in plan_relation_joins(query_graph, join_builder, is_outer=True, tree=query_graph.subquery_join_tree)
            if j.node not in subquery_join_nodes
        ]

    inner_order = plan_order(
        query_graph,
        ctx,
        agg_plan,
        [*filt.joins, *subquery_tree_joins],
        db_features,
        default_order_by,
        deterministic_ordering,
    )

    # Inner projection: needed only for the set of selection function references so the
    # right aggregation columns are hoisted into the subquery (its columns are discarded).
    inner_proj = plan_projection(query_graph, ctx, agg_plan, hook_applier)
    referenced_functions = _referenced_function_nodes(filt, inner_order, inner_proj)

    # Phase 2: assemble the inner subquery statement (mirrors SubqueryBuilder.build).
    inner_joins = _dedup_agg_joins([*filt.joins, *inner_order.joins, *subquery_tree_joins])
    selected_function_labels = {fn: agg_plan.columns[fn] for fn in referenced_functions}
    inner_statement, rank_label = _assemble_inner_statement(
        query_graph,
        ctx,
        hook_applier,
        inner_alias=inner_alias,
        distinct_on=distinct_on,
        use_distinct_on=use_distinct_on,
        inner_joins=inner_joins,
        where=filt.where,
        order_expressions=inner_order.expressions,
        selected_function_columns=tuple(selected_function_labels.values()),
        limit=limit,
        offset=offset,
        statement=statement,
    )

    subquery = inner_statement.subquery(name)
    outer_alias = cast("AliasedClass[Any]", aliased(class_mapper(model), subquery, name=name))

    # Phase 3: re-root onto the materialized subquery and build the outer query.
    ctx.replace(alias=outer_alias)

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

    outer_joins = list(plan_relation_joins(query_graph, join_builder, is_outer=True))
    outer_order = plan_order(
        query_graph,
        ctx,
        outer_agg_plan,
        outer_joins,
        db_features,
        default_order_by,
        deterministic_ordering,
    )
    outer_joins.extend(outer_order.joins)

    root_agg_map: dict[QueryNodeType, Label[Any]] = {}
    if query_graph.selection_tree and query_graph.selection_tree.graph_metadata.metadata.root_aggregations:
        root_agg_map = plan_root_aggregations(query_graph, ctx)
    root_aggs: tuple[Label[Any], ...] = tuple(root_agg_map.values())

    outer_proj = plan_projection(query_graph, ctx, outer_agg_plan, hook_applier)
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
        hook_applier=hook_applier,
        column_map=column_map,
    )


def plan_query(
    query_graph: QueryGraph[Any],
    ctx: AliasContext[Any],
    db_features: DatabaseFeatures,
    dialect: Any,
    hook_applier: Any,
    join_builder: Callable[[QueryNodeType, bool], Join],
    limit: int | None = None,
    offset: int | None = None,
    allow_null: bool = False,
    default_order_by: Sequence[OrderByExpr] = (),
    deterministic_ordering: bool = False,
    statement: Select[Any] | None = None,
) -> QueryPlan:
    """Composes pure passes into a QueryPlan for the non-subquery case.

    Orchestrates ``plan_aggregations``, ``plan_filter``, ``plan_order``,
    ``plan_relation_joins``, ``plan_projection``, and ``plan_root_aggregations``
    into an immutable ``QueryPlan``, matching the non-subquery branch of
    ``QueryTranspiler._build_plan`` exactly.

    Cross-pass aggregation-join deduplication is applied when assembling the
    final join list: each ``AggregationJoin`` node appears at most once, in
    first-seen order across filter → order → projection passes.

    Args:
        query_graph: The graph representation of the query being planned.
        ctx: The query scope (read-only).
        db_features: Database-capability flags.
        dialect: The SQLAlchemy dialect for expression building.
        hook_applier: The HookApplier instance for collecting load options and
            applying statement hooks.
        join_builder: Callable ``(node, is_outer) -> Join`` for constructing
            relation joins.
        limit: Optional pagination limit.
        offset: Optional pagination offset.
        allow_null: Whether to allow null values in filter conditions.
        default_order_by: Default ordering applied when the client supplies none.
        deterministic_ordering: Whether to append PK tiebreaker columns.
        statement: Optional base filter Select statement.  When provided and
            the non-subquery path is taken, a PK semi-join is built and included
            in the plan.

    Returns:
        The assembled ``QueryPlan``.
    """
    distinct_on_rank = _use_distinct_rank_pure(query_graph, db_features, deterministic_ordering, default_order_by)

    subquery_needed = ctx.is_root and (limit is not None or offset is not None or distinct_on_rank)
    if subquery_needed:
        return _plan_subquery(
            query_graph,
            ctx,
            db_features,
            dialect,
            hook_applier,
            join_builder,
            limit=limit,
            offset=offset,
            allow_null=allow_null,
            default_order_by=default_order_by,
            deterministic_ordering=deterministic_ordering,
            statement=statement,
            distinct_on_rank=distinct_on_rank,
        )

    distinct_on = DistinctOn(query_graph)
    use_distinct_on = not distinct_on_rank

    # Pass 1: aggregations (built once, shared by all passes).
    aggregation_plan = plan_aggregations(query_graph, ctx, db_features)
    # Pass 2: filter — yields WHERE predicates and the relation/agg joins they require.
    filter_plan = plan_filter(query_graph, ctx, aggregation_plan, dialect, join_builder, allow_null)
    # Nodes already covered by filter joins; used to exclude duplicates from tree gathers.
    subquery_join_nodes: set[QueryNodeType] = {j.node for j in filter_plan.joins}

    # Pass 3a: gather subquery_join_tree relation joins (outer, filtered).
    subquery_tree_joins: list[Join] = []
    if query_graph.subquery_join_tree:
        subquery_tree_joins = [
            join
            for join in plan_relation_joins(
                query_graph, join_builder, is_outer=True, tree=query_graph.subquery_join_tree
            )
            if join.node not in subquery_join_nodes
        ]

    # Pass 3b: gather root_join_tree relation joins (outer, filtered).
    root_tree_joins: list[Join] = [
        join
        for join in plan_relation_joins(query_graph, join_builder, is_outer=True)
        if join.node not in subquery_join_nodes
    ]

    # All relation joins assembled for _relation_order_by: filter → subquery_tree → root_tree.
    # Passed to plan_order so _relation_order_by sees the full relation-join set (agg
    # joins in filt.joins are skipped by _relation_order_by_pure via isinstance check).
    all_relation_joins: list[Join] = [*filter_plan.joins, *subquery_tree_joins, *root_tree_joins]

    # Pass 4: order — includes _relation_order_by against the full relation-join set.
    order = plan_order(
        query_graph, ctx, aggregation_plan, all_relation_joins, db_features, default_order_by, deterministic_ordering
    )

    # Pass 5: root aggregations.
    root_agg_map: dict[QueryNodeType, Label[Any]] = {}
    if query_graph.selection_tree and query_graph.selection_tree.graph_metadata.metadata.root_aggregations:
        root_agg_map = plan_root_aggregations(query_graph, ctx)
    root_aggs: tuple[Label[Any], ...] = tuple(root_agg_map.values())

    # Pass 6: projection — yields extra columns, load options, selection agg joins, hooks.
    projection_plan = plan_projection(query_graph, ctx, aggregation_plan, hook_applier)

    # Assemble final join list in legacy _build_plan order:
    #   filter.joins → order.joins → subquery_tree(filtered) → root_tree(filtered) → projection.aggregation_joins
    # This matches the non-subquery branch of _build_plan exactly:
    #   joins (filter) → order_by.joins → subquery_tree joins → root_tree joins → aggregation_joins (from _collect_select)
    pre_dedup_joins: list[Join] = [
        *filter_plan.joins,
        *order.joins,
        *subquery_tree_joins,
        *root_tree_joins,
        *projection_plan.aggregation_joins,
    ]

    # Cross-pass aggregation-join deduplication: keep first-seen AggregationJoin per node.
    deduped_joins = _dedup_agg_joins(pre_dedup_joins)

    # Build filter semijoin when a base statement is provided (non-subquery path only).
    filter_semijoin: FilterSemiJoin | None = None
    if statement is not None:
        filter_semijoin = _build_filter_semijoin_pure(ctx, statement)

    # Mirror _build_plan: {**collector.columns, **transform_map, **root_agg_map}.
    column_map: dict[QueryNodeType, ColumnElement[Any]] = {
        **aggregation_plan.columns,
        **projection_plan.transform_map,
        **root_agg_map,
    }

    return QueryPlan(
        root=ctx.root_alias,
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
        hook_applier=hook_applier,
        column_map=column_map,
    )
