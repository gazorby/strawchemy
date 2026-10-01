"""The client's filter as WHERE predicates on a level's rows, with the joins and EXISTS subqueries they need."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, TypeAlias

from sqlalchemy import and_, exists, inspect, not_, null, or_, select, true, tuple_
from sqlalchemy.orm import aliased, class_mapper
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, False_, True_
from sqlalchemy.sql.util import ClauseAdapter

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.dto.strawberry import AggregationFilter, CustomFilter, ExistsFilter, NotExistsFilter
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.transpiler._core.functions import AggregateFunction
from strawchemy.transpiler._core.pipeline import PassBase

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from sqlalchemy.sql import ColumnElement

    from strawchemy.dto.strawberry import Filter
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.rowset import RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("Filtering",)


_Predicates: TypeAlias = "tuple[list[ColumnElement[bool]], RowSet]"
_FilterValue: TypeAlias = "Filter | AggregationFilter | GraphQLComparison | CustomFilter | ExistsFilter"


class Filtering(PassBase):
    """Restricts a level's rows to those passing its filter, split by the request for the level's filter scope.

    Relations every row must have are inner-joined; the others are outer-joined. The split decides which branches are
    tested in an EXISTS and which on the rows.
    """

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        split = level.request.filter_split
        where: list[ColumnElement[bool]] = []
        if split.direct:
            where, rows = _conjunctions(
                level, split.direct, rows, inner_joined=set(split.join_path), allow_null=level.request.allow_null
            )
            for node in split.join_path:
                if node.value.is_relation:
                    _, rows = level.node_alias(node, rows)
        if split.exists is not None:
            where.append(level.plan_exists(split.exists))
        return rows.with_where(*where) if where else rows


def _is_never_unknown(expression: ColumnElement[bool]) -> bool:
    return isinstance(expression, (True_, False_)) or (
        isinstance(expression, BinaryExpression) and expression.operator in {operators.is_, operators.is_not}
    )


def _has_many_predicates(expressions: Sequence[ColumnElement[bool]]) -> bool:
    """Tells whether there are several predicates, counting those inside a single ``and_`` or ``or_``."""
    return len(expressions) > 1 or (isinstance(expressions[0], BooleanClauseList) and len(expressions[0]) > 1)


def _comparison(level: Level, comparison: GraphQLComparison, rows: RowSet, *, not_null_check: bool) -> _Predicates:
    column, rows = level.path_column(comparison.field_node, rows)
    expressions: list[ColumnElement[bool]] = comparison.to_expressions(level.context.dialect, column)
    # Under NOT, a NULL column must fail the comparison rather than make it unknown. Skipped for null tests and
    # constants, which are never unknown, and for empty comparisons, which it would turn into a predicate.
    if not_null_check and expressions and not all(map(_is_never_unknown, expressions)):
        expressions.append(column.is_not(null()))
    return expressions, rows


def _custom_filter(level: Level, custom: CustomFilter, rows: RowSet) -> tuple[ColumnElement[bool], RowSet]:
    """Turns a custom filter into one predicate: a primary-key ``IN`` or a correlated ``EXISTS``.

    The user callback edits a separate ``select(model)``. Matching its primary keys to the outer query's keeps the
    result usable under AND, OR and NOT.
    """
    model = custom.field_node.value.model
    mapper = class_mapper(model)
    inner_pks = SQLAlchemyInspector.pk_attributes(mapper)
    outer_alias, rows = level.node_alias(custom.field_node, rows)
    outer_pks = [pk.adapt_to_entity(inspect(outer_alias)) for pk in inner_pks]

    isolated = custom.apply(select(model), custom.value, dialect=level.context.dialect, model=model)
    # The outer query aliases the root model with its table name. An inner read under that same name would compare
    # the table's keys to themselves and match every outer row; the name also marks the read as user SQL.
    inner_alias = aliased(mapper, flat=True, name="custom_filter")
    adapter = ClauseAdapter(inspect(inner_alias).selectable)
    adapted_pks = [adapter.traverse(pk.__clause_element__()) for pk in inner_pks]
    adapted_select = adapter.traverse(isolated.with_only_columns(*adapted_pks))

    if custom.join == "in":
        if len(outer_pks) == 1:
            # A plain IN is better supported and optimized than a one-element tuple IN.
            return outer_pks[0].in_(adapted_select), rows
        return tuple_(*outer_pks).in_(adapted_select), rows

    correlation = and_(*[inner == outer for inner, outer in zip(adapted_pks, outer_pks, strict=True)])
    return exists(adapted_select.where(correlation)).correlate(outer_alias), rows


def _aggregation_filter(level: Level, aggregation: AggregationFilter, rows: RowSet) -> _Predicates:
    function = AggregateFunction.for_filter(aggregation.field_node, distinct=aggregation.distinct)
    column, rows = level.aggregate(function, rows)
    return aggregation.predicate.to_expressions(level.context.dialect, column), rows


def _exists_filter(
    level: Level,
    exists_filter: ExistsFilter,
    rows: RowSet,
    *,
    inner_joined: Collection[QueryNodeType],
    not_null_check: bool,
) -> tuple[ColumnElement[bool], RowSet]:
    """Tests the nested filter in an EXISTS correlated to the rows of its node, a NOT EXISTS for ``_not``.

    A filter the split tests on the rows is as true as its EXISTS would be: never unknown where that matters.
    """
    negated = isinstance(exists_filter, NotExistsFilter)
    if (rows_filter := level.request.filter_split.rows_filter(exists_filter)) is not None:
        predicates, rows = _conjunctions(level, rows_filter, rows, inner_joined=inner_joined)
        tested = and_(*predicates)
        if negated:
            return tested.is_not(true()), rows
        return (tested.is_(true()) if not_null_check else tested), rows
    alias, rows = level.node_alias(exists_filter.field_node, rows)
    node_level = replace(level, alias=alias, request=replace(level.request, allow_null=False))
    return node_level.plan_exists(exists_filter.dto_filter, negated=negated), rows


def _gather_conjunctions(
    level: Level,
    values: Sequence[_FilterValue],
    rows: RowSet,
    *,
    inner_joined: Collection[QueryNodeType],
    not_null_check: bool = False,
) -> _Predicates:
    """Builds the predicates of each filter in ``values``."""
    expressions: list[ColumnElement[bool]] = []
    for value in values:
        if isinstance(value, AggregationFilter):
            predicates, rows = _aggregation_filter(level, value, rows)
            expressions.extend(predicates)
        elif isinstance(value, GraphQLComparison):
            predicates, rows = _comparison(level, value, rows, not_null_check=not_null_check)
            expressions.extend(predicates)
        elif isinstance(value, CustomFilter):
            predicate, rows = _custom_filter(level, value, rows)
            expressions.append(predicate)
        elif isinstance(value, ExistsFilter):
            predicate, rows = _exists_filter(
                level, value, rows, inner_joined=inner_joined, not_null_check=not_null_check
            )
            expressions.append(predicate)
        else:
            predicates, rows = _conjunctions(level, value, rows, inner_joined=inner_joined, allow_null=not_null_check)
            if predicates:
                and_expression = and_(*predicates)
                expressions.append(and_expression.self_group() if _has_many_predicates(predicates) else and_expression)
    return expressions, rows


def _conjunctions(
    level: Level,
    query: Filter,
    rows: RowSet,
    *,
    inner_joined: Collection[QueryNodeType],
    allow_null: bool = False,
) -> _Predicates:
    """Builds the predicates of a filter's AND, OR and NOT branches."""
    expressions: list[ColumnElement[bool]] = []
    and_expressions, rows = _gather_conjunctions(
        level, query.and_, rows, inner_joined=inner_joined, not_null_check=allow_null
    )
    or_expressions, rows = _gather_conjunctions(
        level, query.or_, rows, inner_joined=inner_joined, not_null_check=allow_null
    )
    if query.not_:
        not_expressions, rows = _gather_conjunctions(
            level, [query.not_], rows, inner_joined=inner_joined, not_null_check=True
        )
        if not_expressions:
            and_expressions.append(not_(and_(*not_expressions)))
    if and_expressions:
        and_expression = and_(*and_expressions)
        if or_expressions and _has_many_predicates(and_expressions):
            and_expression = and_expression.self_group()
        expressions.append(and_expression)
    if or_expressions:
        or_expression = or_(*or_expressions)
        if and_expressions and _has_many_predicates(or_expressions):
            or_expression = or_expression.self_group()
        expressions.append(or_expression)
    if query.relation is not None and query.relation not in inner_joined:
        # Outer-joined, a missing related row would pass predicates such as ``isNull`` or ``_not``.
        alias, rows = level.node_alias(query.relation, rows)
        primary_key = SQLAlchemyInspector.pk_attributes(inspect(alias).mapper)[0]
        expressions.append(primary_key.adapt_to_entity(inspect(alias)).is_not(null()))
    return expressions, rows
