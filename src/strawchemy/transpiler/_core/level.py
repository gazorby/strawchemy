"""The scope every pass plans in: one SQL level, and the pure services reading its columns and joins."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from sqlalchemy import and_, func, inspect, literal_column, not_, select, true
from sqlalchemy import cast as sqla_cast
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import QueryableAttribute, RelationshipProperty, aliased

from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector, SQLAlchemyInspector
from strawchemy.exceptions import TranspilingError
from strawchemy.transpiler._core import functions
from strawchemy.transpiler._core.attach import RankWindow, attach_grouped, correlate_relation
from strawchemy.transpiler._core.materialize import materialize, materialize_shared
from strawchemy.transpiler._core.render import clause_element, priority_sorted, render_rows
from strawchemy.transpiler._core.request import QueryRequest
from strawchemy.transpiler._core.rowset import AggregateJoin, Join, Projection, RowSet
from strawchemy.utils.postgres import as_jsonb

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import Dialect, Label, Select
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.dto.strawberry import BooleanFilterDTO
    from strawchemy.transpiler._core.functions import AggregateFunction
    from strawchemy.transpiler._core.pipeline import Pipelines
    from strawchemy.transpiler._core.plan import QueryPlan
    from strawchemy.transpiler._core.rowset import JoinKey, StatementEdit
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import OrderByExpr, QueryNodeType, SupportedDialect

__all__ = ("Level", "LevelKind", "PlanContext")


_Scope = TypeVar("_Scope", RowSet, Projection)

LevelKind = Literal["root", "relation", "exists", "dml"]


@dataclass(frozen=True)
class PlanContext:
    """Settings shared by every level of one query."""

    dialect: Dialect
    db_features: DatabaseFeatures
    inspector: SQLAlchemyGraphQLInspector
    pipelines: Pipelines
    query_hooks: Mapping[QueryNodeType, Sequence[QueryHook[Any]]]
    default_order_by: tuple[OrderByExpr, ...] = ()
    """Ordering used when the client asks for none."""
    deterministic_ordering: bool = False
    """Adds primary-key columns to ORDER BY so that row order is stable."""
    statement: Select[Any] | None = None
    """User statement restricting the root rows."""

    @classmethod
    def create(
        cls,
        model: type[DeclarativeBase],
        dialect: Dialect,
        *,
        pipelines: Pipelines,
        statement: Select[Any] | None = None,
        query_hooks: Mapping[QueryNodeType, Sequence[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> PlanContext:
        """Builds the context of a query on ``model``."""
        inspector = SQLAlchemyGraphQLInspector(cast("SupportedDialect", dialect.name), [model.registry])
        return cls(
            dialect=dialect,
            db_features=inspector.db_features,
            inspector=inspector,
            pipelines=pipelines,
            query_hooks=query_hooks or {},
            default_order_by=tuple(default_order_by or ()),
            deterministic_ordering=deterministic_ordering,
            statement=statement,
        )


@dataclass(frozen=True)
class Level:
    """One SQL level: the root query, a relation planned on its own, an EXISTS subquery or a DML filter.

    Services never change a RowSet or Projection: they return a new one holding the joins they added, each stored
    under its key with the alias it reads from, so a later call finds it instead of joining again.
    """

    request: QueryRequest
    context: PlanContext
    node: QueryNodeType
    """The root node, or the relation node this level stands for."""
    alias: AliasedClass[Any]
    """This level's FROM."""
    parent: Level | None = None
    kind: LevelKind = "root"
    row_joins: Mapping[JoinKey, Join] = field(default_factory=dict)
    """Row-stage joins of the levels above, which a relation planned on one of their aliases reuses."""

    @property
    def _dialect(self) -> SupportedDialect:
        return self.context.db_features.dialect

    def _hops(self, node: QueryNodeType) -> list[QueryNodeType]:
        """Returns the relation nodes between this level's node and ``node``, outermost first."""
        hops: list[QueryNodeType] = []
        parent = node.parent
        while parent is not None and parent.value.is_relation and parent != self.node:
            hops.append(parent)
            parent = parent.parent
        return hops[::-1]

    def _joined_alias(
        self, node: QueryNodeType, scope: _Scope, reuse: RowSet | None = None
    ) -> tuple[AliasedClass[Any], _Scope]:
        """Returns the alias ``node`` is read from, and ``scope`` with the relation joins that reach it.

        A join already in ``reuse`` or ``scope`` is reused; a missing one is added to ``scope``.
        """
        alias = self.alias
        for hop in self._hops(node):
            key: JoinKey = ("relation", hop)
            join = (reuse.join(key) if reuse is not None else None) or scope.joins.get(key)
            if join is None:
                join = self._relation_join(hop, alias)
                scope = cast("_Scope", scope.with_join(join))
            assert join.alias is not None
            alias = join.alias
        return alias, scope

    def _relation_join(self, node: QueryNodeType, parent_alias: AliasedClass[Any]) -> Join:
        """Joins the relation of ``node``, inner when the filter goes through it so that it drops unmatched rows."""
        relationship = cast("RelationshipProperty[Any]", node.value.model_field.property)
        target = aliased(relationship.mapper, flat=True)
        onclause = getattr(parent_alias, relationship.key).of_type(target)
        is_outer = node not in self.request.filter_split.join_path
        return Join(("relation", node), target, onclause, is_outer, target)

    def _aggregate_join(
        self,
        aggregation_node: QueryNodeType,
        parent_alias: AliasedClass[Any],
        computed: Mapping[QueryNodeType, AggregateFunction] | None = None,
    ) -> AggregateJoin:
        """Builds the join computing ``computed``, by default every function the request uses on the node."""
        relation: QueryableAttribute[Any] = aggregation_node.value.model_field
        relationship = cast("RelationshipProperty[Any]", relation.property)
        function_alias = aliased(relationship.mapper, flat=True)
        if computed is None:
            computed = self.request.aggregate_functions(aggregation_node)
        calls: dict[tuple[Any, ...], Label[Any]] = {}
        labels: dict[QueryNodeType, Label[Any]] = {}
        for function_node, function in computed.items():
            if (call := _call(function)) not in calls:
                calls[call] = functions.build(function, function_alias, self._dialect)
            labels[function_node] = calls[call]
        return attach_grouped(
            labels, aggregation_node, relation, parent_alias, function_alias, self.context.db_features
        )

    def _read(self, node: QueryNodeType, alias: AliasedClass[Any]) -> ColumnElement[Any]:
        attribute: QueryableAttribute[Any] = node.value.model_field.adapt_to_entity(inspect(alias))
        if json_path := node.metadata.data.json_path:
            return _extract_json(attribute, json_path, self._dialect)
        return attribute.__clause_element__()

    def _plan_relation(
        self,
        node: QueryNodeType,
        request: QueryRequest,
        alias: AliasedClass[Any],
        row_joins: Mapping[JoinKey, Join] | None = None,
    ) -> QueryPlan:
        return self.context.pipelines.relation.plan(self._relation_level(node, request, alias, row_joins))

    def _relation_level(
        self,
        node: QueryNodeType,
        request: QueryRequest,
        alias: AliasedClass[Any],
        row_joins: Mapping[JoinKey, Join] | None = None,
    ) -> Level:
        return Level(
            request=request,
            context=self.context,
            node=node,
            alias=alias,
            parent=self,
            kind="relation",
            row_joins=row_joins or {},
        )

    def _sibling_joins(self, requests: Sequence[QueryRequest]) -> dict[JoinKey, Join]:
        """Builds one join per relation path that several sibling ``requests`` read, keyed under each reading node."""
        by_relation: dict[tuple[bool, QueryableAttribute[Any]], list[tuple[QueryNodeType, QueryRequest]]] = {}
        for request in requests:
            relations = Counter(
                child.value.model_field
                for child in request.selection.children
                if child.value.is_relation and not child.value.is_computed
            )
            for child in request.selection.children:
                # ``plan_child`` reuses a relation join only for a relation without arguments or hooks of its own, and
                # not aliased in its parent, whose aliases ``plan_siblings`` plans under a join key of their own.
                if child.value.is_aggregate or (
                    child.value.is_relation
                    and not child.value.is_computed
                    and relations[child.value.model_field] == 1
                    and not QueryRequest.for_relation(child).orders_rows
                    and not self.hooks(child)
                ):
                    key = (child.value.is_aggregate, child.value.model_field)
                    by_relation.setdefault(key, []).append((child, request))
        joins: dict[JoinKey, Join] = {}
        for (is_aggregate, _), readers in by_relation.items():
            if len(readers) < 2:  # noqa: PLR2004
                continue
            first = readers[0][0]
            if is_aggregate:
                computed = {
                    function_node: function
                    for child, request in readers
                    for function_node, function in request.aggregate_functions(child).items()
                }
                join: Join = self._aggregate_join(first, self.alias, computed)
            else:
                join = self._relation_join(first, self.alias)
            joins.update({(join.key[0], child): join for child, _ in readers})
            if not is_aggregate:
                assert join.alias is not None
                child_requests = [QueryRequest.for_relation(child) for child, _ in readers]
                child_level = self._relation_level(first, child_requests[0], join.alias)
                joins.update(child_level._sibling_joins(child_requests))  # noqa: SLF001
        return joins

    def _plain_join(self, node: QueryNodeType, rows: RowSet) -> Join:
        """Left-joins the inlined ``rows`` of relation ``node``, their WHERE and their hooks' in the ON clause."""
        relation = getattr(self.alias, node.value.model_field.key).of_type(rows.source)
        edits_where = rows.edits_where()
        where = (*rows.where, *(() if edits_where is None else (edits_where,)))
        if where:
            relation = relation.and_(*where)
        return Join(("relation", node), rows.source, relation, True, rows.source, criteria=where)

    def _plan_exists_rows(self, dto_filter: BooleanFilterDTO, alias: AliasedClass[Any]) -> RowSet:
        request = replace(self.request, dto_filter=dto_filter, filter_scope="exists")
        level = Level(request=request, context=self.context, node=self.node, alias=alias, parent=self, kind="exists")
        return self.context.pipelines.exists.plan(level).rows

    def _correlated_exists(self, rows: RowSet, leaving: Sequence[Join]) -> ColumnElement[bool]:
        """Builds the EXISTS of ``rows`` from the ``leaving`` joins, each correlated to this level's alias."""
        first = leaving[0]
        leaving_keys = {join.key for join in leaving}

        def correlate(statement: Select[Any]) -> Select[Any]:
            for join in leaving:
                if join is not first:
                    statement = statement.select_from(join.target)
                relation = cast("QueryableAttribute[Any]", join.onclause)
                statement = correlate_relation(statement, relation, cast("AliasedClass[Any]", join.target))
            return statement

        source = cast("AliasedClass[Any]", first.target)
        # This level's alias is the enclosing query's row, correlated rather than a FROM of the body: a join from it,
        # such as a LATERAL of its aggregates, starts from the body's first FROM instead.
        body = replace(
            rows,
            source=source,
            joins={
                key: replace(join, left=source) if join.left is self.alias else join
                for key, join in rows.joins.items()
                if key not in leaving_keys
            },
            edits=(correlate,),
        )
        statement = render_rows(body, [literal_column("1")], self.context.db_features).statement
        return statement.exists().correlate(self.alias)

    def _exists_on_copy(self, dto_filter: BooleanFilterDTO, *, derived_table: bool) -> ColumnElement[bool]:
        """Builds the EXISTS of ``dto_filter`` on a copy of this level's model, matched on every primary key.

        With ``derived_table``, the matched keys are read through a derived table.
        """
        mapper = inspect(self.alias).mapper
        copy = aliased(mapper, flat=True)
        rows = self._plan_exists_rows(dto_filter, copy)
        keys = [attribute.key for attribute in SQLAlchemyInspector.pk_attributes(mapper)]
        matched: Sequence[ColumnElement[Any]] = [clause_element(getattr(copy, key)) for key in keys]
        columns = matched if derived_table else [literal_column("1")]
        statement = render_rows(rows, columns, self.context.db_features).statement
        if derived_table:
            derived = statement.subquery("dml_matched")
            matched = list(derived.c)[: len(keys)]
            statement = select(literal_column("1")).select_from(derived)
        correlation = [column == getattr(self.alias, key) for column, key in zip(matched, keys, strict=True)]
        return statement.where(and_(*correlation)).exists().correlate(self.alias)

    def _plan_children(self, nodes: Sequence[QueryNodeType], rows: RowSet, projection: Projection) -> Projection:
        for node in nodes:
            projection = self.plan_child(node, rows, projection)
        return projection

    @classmethod
    def root(cls, request: QueryRequest, context: PlanContext) -> Level:
        model = request.model
        alias = aliased(model.__mapper__, name=model.__tablename__, flat=True)
        return cls(request=request, context=context, node=request.selection.root, alias=alias)

    @classmethod
    def dml(cls, request: QueryRequest, context: PlanContext) -> Level:
        """Creates a level whose alias reads the table's own columns, as UPDATE and DELETE need in their WHERE."""
        model = request.model
        alias = aliased(model.__mapper__, model.__table__)
        return cls(request=request, context=context, node=request.selection.root, alias=alias, kind="dml")

    def hooks(self, node: QueryNodeType) -> Sequence[QueryHook[Any]]:
        return self.context.query_hooks.get(node, ())

    def column(self, node: QueryNodeType) -> ColumnElement[Any]:
        """Returns the column of ``node``, a direct field of this level's model, with its JSON path extracted."""
        return self._read(node, self.alias)

    def primary_keys(self) -> tuple[ColumnElement[Any], ...]:
        """Returns the primary-key columns of this level's model, read from ``alias``."""
        alias = inspect(self.alias)
        return tuple(
            clause_element(attribute.adapt_to_entity(alias))
            for attribute in SQLAlchemyInspector.pk_attributes(alias.mapper)
        )

    def path_column(self, node: QueryNodeType, rows: RowSet) -> tuple[ColumnElement[Any], RowSet]:
        """Returns the column of ``node``, reached through the relations above it, and ``rows`` with their joins."""
        alias, rows = self._joined_alias(node, rows)
        return self._read(node, alias), rows

    def node_alias(self, node: QueryNodeType, rows: RowSet) -> tuple[AliasedClass[Any], RowSet]:
        """Returns the alias the rows of ``node``, a root or relation node, are read from, and ``rows`` joining it."""
        alias, rows = self._joined_alias(node, rows)
        if not node.value.is_relation:
            return alias, rows
        join = rows.join(("relation", node)) or self._relation_join(node, alias)
        assert join.alias is not None
        return join.alias, rows.with_join(join)

    def aggregate(self, function: AggregateFunction, rows: RowSet) -> tuple[ColumnElement[Any], RowSet]:
        """Returns the column of ``function`` and ``rows`` holding the aggregate join that computes it."""
        aggregation_node = _aggregation_node(function)
        join = rows.join(("aggregate", aggregation_node))
        if join is None:
            parent_alias, rows = self._joined_alias(aggregation_node, rows)
            join = self._aggregate_join(aggregation_node, parent_alias)
            rows = rows.with_join(join)
        return _aggregate_column(join, function), rows

    def projected_aggregate(
        self, function: AggregateFunction, rows: RowSet, projection: Projection
    ) -> tuple[ColumnElement[Any], Projection]:
        """Returns the column of ``function``, from a row-stage join if any, else from one added to ``projection``."""
        key: JoinKey = ("aggregate", _aggregation_node(function))
        join = rows.join(key) or self.row_joins.get(key) or projection.joins.get(key)
        if join is None:
            parent_alias, projection = self._joined_alias(key[1], projection, reuse=rows)
            join = self._aggregate_join(key[1], parent_alias)
            projection = projection.with_join(join)
        return _aggregate_column(join, function), projection

    def plan_child(self, node: QueryNodeType, rows: RowSet, projection: Projection) -> Projection:
        """Plans ``node``, a selected relation of this level's model, and merges what it reads into ``projection``.

        Without ordering, pagination, DISTINCT ON or hooks adding WHERE or JOIN, the relation reads the row-stage join
        of ``node``. Otherwise it gets its own join: a plain join carrying its hooks' WHERE in the ON clause, or the
        LATERAL or CTE join of ``attach_rows``, whose ORDER BY the merged projection carries at ``CLIENT`` priority.
        """
        key: JoinKey = ("relation", node)
        request = QueryRequest.for_relation(node)
        reused = rows.join(key) or self.row_joins.get(key)
        if reused is not None and reused.alias is not None and not request.orders_rows:
            plan = self._plan_relation(node, request, reused.alias, {**self.row_joins, **rows.joins})
            inlined = plan.join_to_parent is None and _is_bare(replace(plan.rows, edits=()))
            if inlined and plan.rows.edits_where() is None:
                return projection.merge(plan.projection)
        relationship = cast("RelationshipProperty[Any]", node.value.model_field.property)
        plan = self._plan_relation(node, request, aliased(relationship.mapper, flat=True))
        join = plan.join_to_parent or self._plain_join(node, plan.rows)
        return projection.with_join(join).merge(plan.projection)

    def plan_siblings(self, nodes: tuple[QueryNodeType, ...], rows: RowSet, projection: Projection) -> Projection:
        """Plans ``nodes``, aliases of one relation of this level's model, as one read merged into ``projection``."""
        pipeline = self.context.pipelines.relation
        relationship = cast("RelationshipProperty[Any]", nodes[0].value.model_field.property)
        target = aliased(relationship.mapper, flat=True)
        requests = [QueryRequest.for_relation(node) for node in nodes]
        levels = [self._relation_level(node, request, target) for node, request in zip(nodes, requests, strict=True)]
        level_rows = [pipeline.rows(level) for level in levels]
        shared = replace(level_rows[0], order_by=(), limit=None, offset=None)
        # Ranks are computed before an edit's LIMIT, DISTINCT or GROUP BY, which would then keep arbitrary rows.
        if shared.edits_shape_rows() or not all(_same_rows(alias_rows, shared) for alias_rows in level_rows):
            return self._plan_children(nodes, rows, projection)
        joins = levels[0]._sibling_joins(requests)  # noqa: SLF001
        merged = Projection()
        windows: list[RankWindow] = []
        for level, alias_rows in zip(levels, level_rows, strict=True):
            merged = merged.merge(pipeline.project(replace(level, row_joins=joins), alias_rows))
            order_by = tuple(term for _, term in priority_sorted(alias_rows.order_by))
            # An offset of 0 bounds nothing; as a bound it would keep the page filter that an unbounded alias drops.
            windows.append(RankWindow(level.node, order_by, alias_rows.offset or None, alias_rows.limit))
        for join in {id(join): join for join in joins.values()}.values():
            merged = merged.with_join(join)
        join, shared_projection = materialize_shared(self, shared, merged, windows)
        return projection.with_join(join).merge(shared_projection)

    def plan_exists(self, dto_filter: BooleanFilterDTO, *, negated: bool = False) -> ColumnElement[bool]:
        """Returns an EXISTS testing ``dto_filter`` on the relations of this level's rows, correlated to its alias.

        Each relation leaving the alias is inner-joined. A DML filter reads a copy of the table, matched on the primary
        keys, when it aggregates the table's rows and on databases needing a derived table. A filter needing no join
        is returned without EXISTS.

        Raises:
            TranspilingError: If a filter other than DML aggregates this level's rows, which the split tests directly.
        """
        derived_table = self.kind == "dml" and self.context.db_features.dml_subquery_needs_derived_table
        if derived_table:
            expression = self._exists_on_copy(dto_filter, derived_table=True)
        else:
            rows = self._plan_exists_rows(dto_filter, self.alias)
            if not rows.joins and negated:
                # Without EXISTS, a NULL column must fail the filter, as it fails inside the EXISTS.
                checked = replace(self, request=replace(self.request, allow_null=True))
                rows = checked._plan_exists_rows(dto_filter, self.alias)  # noqa: SLF001
            leaving = [join for join in rows.joins.values() if _leaves(join, self.alias)]
            outer = [
                join for join in rows.joins.values() if join.is_outer and (join in leaving or join.left is self.alias)
            ]
            assert all(isinstance(join, AggregateJoin) for join in outer), "filter_split inner-joins every relation"
            if not rows.joins:
                expression = and_(true(), *rows.where)
            elif leaving and not outer:
                expression = self._correlated_exists(rows, leaving)
            elif self.kind == "dml":
                expression = self._exists_on_copy(dto_filter, derived_table=False)
            else:  # pragma: no cover  # defensive: the split tests every aggregate of a level on its rows
                msg = "an EXISTS filter cannot aggregate the rows of its level"
                raise TranspilingError(msg)
        return not_(expression) if negated else expression

    def materialize(self, rows: RowSet, projection: Projection) -> QueryPlan:
        """Inlines ``rows`` next to ``projection`` when they only filter, else renders them as one FROM."""
        return materialize(self, rows, projection)


def _aggregation_node(function: AggregateFunction) -> QueryNodeType:
    return function.node.find_parent(lambda node: node.value.is_aggregate, strict=True)


def _aggregate_column(join: Join, function: AggregateFunction) -> ColumnElement[Any]:
    assert isinstance(join, AggregateJoin)
    return join.columns[function.node]


def _call(function: AggregateFunction) -> tuple[Any, ...]:
    """Returns what tells the SQL calls of two functions apart, so that two nodes asking for one share its column."""
    return function.name, tuple(argument.value.model_field_name for argument in function.arguments), function.distinct


def _extract_json(attribute: QueryableAttribute[Any], json_path: str, dialect: SupportedDialect) -> ColumnElement[Any]:
    """Extracts ``json_path`` from a JSON column, giving an empty object when the value is missing."""
    if dialect == "postgresql":
        transform = func.coalesce(
            func.jsonb_path_query_first(as_jsonb(attribute), sqla_cast(json_path, postgresql.JSONPATH)),
            sqla_cast({}, postgresql.JSONB),
        )
    else:
        transform = func.coalesce(attribute.op("->")(json_path), func.json_object())
    return transform.label(None)


def _same_edit(left: StatementEdit, right: StatementEdit) -> bool:
    """Tells whether two edits are one, or partials of one function with the same arguments, as hooks' are."""
    if left is right:
        return True
    return (
        isinstance(left, partial)
        and isinstance(right, partial)
        and left.func == right.func
        and _same_objects(left.args, right.args)
        and left.keywords.keys() == right.keywords.keys()
        and all(left.keywords[name] is right.keywords[name] for name in left.keywords)
    )


def _same_objects(left: Sequence[object], right: Sequence[object]) -> bool:
    return len(left) == len(right) and all(first is second for first, second in zip(left, right, strict=True))


def _same_rows(left: RowSet, right: RowSet) -> bool:
    """Tells whether ``left`` and ``right`` select the same rows, whatever their order, limit and offset."""
    return (
        left.source is right.source
        and _same_objects(tuple(left.joins.values()), tuple(right.joins.values()))
        and _same_objects(left.where, right.where)
        and _same_objects(left.distinct_on, right.distinct_on)
        and len(left.edits) == len(right.edits)
        and all(_same_edit(first, second) for first, second in zip(left.edits, right.edits, strict=True))
    )


def _is_bare(rows: RowSet) -> bool:
    """Tells whether ``rows`` add nothing to their source."""
    return rows == RowSet.over(rows.source)


def _leaves(join: Join, alias: AliasedClass[Any]) -> bool:
    """Tells whether ``join`` is a relation join whose parent is ``alias``."""
    onclause = join.onclause
    return isinstance(onclause, QueryableAttribute) and onclause.parent is inspect(alias)
