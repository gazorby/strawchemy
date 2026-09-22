"""DB-free tests for the planner helpers and the filter-statement handling.

The filter-statement tests drive the public ``plan_query`` entry point (building a
``PlanContext`` and ``QueryGraph`` and compiling the emitted statement) rather than poking
``UserStatementPlan`` directly, so they exercise the real inline-vs-semijoin wiring.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from inline_snapshot import snapshot
from sqlalchemy import ColumnClause, Join, Select, func, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import aliased
from sqlalchemy.sql import visitors

from strawchemy.transpiler._planner import (
    AggregationPlan,
    FilterPhase,
    FilterPlan,
    OrderPlan,
    Plan,
    PlanContext,
    ProjectionPhase,
    ProjectionPlan,
    _dedup_columns,
    _use_distinct_rank,
    plan_query,
)
from strawchemy.transpiler._query import QueryGraph
from tests.unit.models import Fruit
from tests.unit.schemas.secondary_table import schema as secondary_table_schema
from tests.unit.utils import DialectContext
from tests.utils import format_sql

if TYPE_CHECKING:
    from collections.abc import Sequence

    from strawchemy.transpiler._query import Join as QueryJoin


def _filter_statement_sql(statement: Select[tuple[Fruit]], *, limit: int | None = None) -> str:
    """Builds and formats the SQL ``plan_query`` emits for a base ``filter_statement``.

    Compile is DB-free (sqlite dialect); the output is sqlparse-formatted to match the
    integration ``.ambr`` snapshot style.

    Args:
        statement: The user-provided base filter statement applied to the query.
        limit: Optional pagination limit, forcing the inner-subquery path.

    Returns:
        The formatted compiled SQL string for the emitted plan.
    """
    context = PlanContext.create(Fruit, sqlite.dialect(), statement=statement)
    plan = plan_query(QueryGraph(context.aliases), context, limit=limit)
    return format_sql(str(plan.emit().compile(dialect=sqlite.dialect())))


def test_planning_passes_share_the_plan_signature() -> None:
    """Every planning pass and phase builds from a query graph, a context and its own arguments through ``Plan``."""
    context = PlanContext.create(Fruit, sqlite.dialect())
    query_graph = QueryGraph(context.aliases)
    aggregation_pass: type[Plan[[]]] = AggregationPlan
    filter_pass: type[Plan[[AggregationPlan, bool]]] = FilterPlan
    order_pass: type[Plan[[AggregationPlan, Sequence[QueryJoin]]]] = OrderPlan
    projection_pass: type[Plan[[AggregationPlan]]] = ProjectionPlan
    filter_phase: type[Plan[[bool]]] = FilterPhase
    projection_phase: type[Plan[[AggregationPlan]]] = ProjectionPhase

    agg_plan = aggregation_pass.plan(query_graph, context)
    assert isinstance(agg_plan, AggregationPlan)

    assert isinstance(filter_pass.plan(query_graph, context, agg_plan, False), FilterPlan)
    assert isinstance(order_pass.plan(query_graph, context, agg_plan, []), OrderPlan)
    assert isinstance(projection_pass.plan(query_graph, context, agg_plan), ProjectionPlan)
    assert isinstance(filter_phase.plan(query_graph, context, False), FilterPhase)
    assert isinstance(projection_phase.plan(query_graph, context, agg_plan), ProjectionPhase)


def test_dedup_columns_removes_structural_duplicates() -> None:
    """A column repeated via distinct attribute objects is collapsed to one, order preserved."""
    fruit = aliased(Fruit)
    # Capture the aliased attributes as concrete references before building the list.
    id_col, name_col, sweetness_col = fruit.id, fruit.name, fruit.sweetness
    cols = [id_col, name_col, id_col, sweetness_col]

    result = _dedup_columns(cols)  # ty: ignore[invalid-argument-type]

    assert len(result) == 3
    # Verify first-seen order is preserved using object identity.
    assert result == [id_col, name_col, sweetness_col]


def test_dedup_columns_keeps_distinct_columns() -> None:
    """Different columns sharing a name across no aliasing are not collapsed."""
    fruit = aliased(Fruit)
    cols = [fruit.id, fruit.name, fruit.sweetness]

    result = _dedup_columns(cols)  # ty: ignore[invalid-argument-type]

    assert len(result) == 3


def test_dedup_columns_keeps_anonymous_columns_of_one_selectable() -> None:
    """Anonymously-labelled columns compare equal to each other, yet none of them is a duplicate."""
    fruit = aliased(Fruit)
    lateral = select(func.count().label(None), func.sum(fruit.sweetness).label(None)).subquery().lateral()
    count_col, sum_col = lateral.c

    result = _dedup_columns([count_col, sum_col])

    assert result == [count_col, sum_col]


def _distinct_enum(model_field: object) -> SimpleNamespace:
    """Stand-in for an EnumDTO exposing field_definition.model_field."""
    return SimpleNamespace(field_definition=SimpleNamespace(model_field=model_field))


def _order_node(model_field: object) -> SimpleNamespace:
    """Stand-in for a QueryNodeType exposing value.model_field."""
    return SimpleNamespace(value=SimpleNamespace(model_field=model_field))


def test_use_distinct_rank_native_when_postgres_and_prefix() -> None:
    """Postgres + compatible prefix order -> native DISTINCT ON (no rank emulation)."""
    col_name = object()
    graph = SimpleNamespace(
        distinct_on=[_distinct_enum(col_name)],
        order_by_nodes=[_order_node(col_name)],
        order_by_tree=object(),
    )
    context = SimpleNamespace(
        db_features=SimpleNamespace(supports_distinct_on=True),
        deterministic_ordering=False,
        default_order_by=(),
    )
    assert _use_distinct_rank(graph, context) is False  # ty: ignore[invalid-argument-type]


def test_use_distinct_rank_emulates_when_postgres_and_incompatible() -> None:
    """Postgres + ordering that is not a distinct prefix -> rank emulation."""
    col_name, col_id = object(), object()
    graph = SimpleNamespace(
        distinct_on=[_distinct_enum(col_name)],
        order_by_nodes=[_order_node(col_id)],
        order_by_tree=object(),
    )
    context = SimpleNamespace(
        db_features=SimpleNamespace(supports_distinct_on=True),
        deterministic_ordering=False,
        default_order_by=(),
    )
    assert _use_distinct_rank(graph, context) is True  # ty: ignore[invalid-argument-type]


def test_use_distinct_rank_native_when_postgres_and_no_ordering() -> None:
    """Postgres + distinct + no ordering -> native (unchanged behaviour)."""
    col_name = object()
    graph = SimpleNamespace(
        distinct_on=[_distinct_enum(col_name)],
        order_by_nodes=[],
        order_by_tree=None,
    )
    context = SimpleNamespace(
        db_features=SimpleNamespace(supports_distinct_on=True),
        deterministic_ordering=False,
        default_order_by=(),
    )
    assert _use_distinct_rank(graph, context) is False  # ty: ignore[invalid-argument-type]


def test_use_distinct_rank_emulates_when_no_native_support() -> None:
    """Non-postgres dialect always emulates when distinct is present."""
    col_name = object()
    graph = SimpleNamespace(
        distinct_on=[_distinct_enum(col_name)],
        order_by_nodes=[],
        order_by_tree=None,
    )
    context = SimpleNamespace(
        db_features=SimpleNamespace(supports_distinct_on=False),
        deterministic_ordering=False,
        default_order_by=(),
    )
    assert _use_distinct_rank(graph, context) is True  # ty: ignore[invalid-argument-type]


@pytest.mark.inline_snapshot
def test_trivial_filter_statement_is_inlined() -> None:
    """A trivial WHERE-only filter statement is inlined directly, with no PK semi-join."""
    assert _filter_statement_sql(select(Fruit).where(Fruit.name == "x")).splitlines() == snapshot(
        ["SELECT fruit.id", "  FROM fruit AS fruit", " WHERE fruit.name = ?"]
    )


@pytest.mark.inline_snapshot
def test_trivial_filter_statement_is_inlined_in_pagination_subquery() -> None:
    """With pagination the trivial filter is inlined inside the inner subquery, no semi-join."""
    assert _filter_statement_sql(select(Fruit).where(Fruit.name == "x"), limit=5).splitlines() == snapshot(
        [
            "SELECT fruit.id",
            "  FROM (",
            "        SELECT fruit.id AS id",
            "          FROM fruit AS fruit",
            "         WHERE fruit.name = ?",
            "         LIMIT ?",
            "        OFFSET ?",
            "       ) AS fruit",
        ]
    )


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        pytest.param(
            select(Fruit).where(Fruit.name == "x").limit(5),
            snapshot(
                [
                    "SELECT fruit.id",
                    "  FROM fruit AS fruit",
                    "  JOIN (",
                    "        SELECT fruit.id AS id",
                    "          FROM fruit",
                    "         WHERE fruit.name = ?",
                    "         LIMIT ?",
                    "        OFFSET ?",
                    "       ) AS anon_1",
                    "    ON fruit.id = anon_1.id",
                ]
            ),
            id="limit",
        ),
        pytest.param(
            select(Fruit).where(Fruit.name == "x").group_by(Fruit.color_id),
            snapshot(
                [
                    "SELECT fruit.id",
                    "  FROM fruit AS fruit",
                    "  JOIN (",
                    "        SELECT fruit.id AS id",
                    "          FROM fruit",
                    "         WHERE fruit.name = ?",
                    "         GROUP BY fruit.color_id",
                    "       ) AS anon_1",
                    "    ON fruit.id = anon_1.id",
                ]
            ),
            id="group_by",
        ),
        pytest.param(
            select(Fruit).where(Fruit.name == "x").distinct(),
            snapshot(
                [
                    "SELECT fruit.id",
                    "  FROM fruit AS fruit",
                    "  JOIN (",
                    "        SELECT DISTINCT fruit.id AS id",
                    "          FROM fruit",
                    "         WHERE fruit.name = ?",
                    "       ) AS anon_1",
                    "    ON fruit.id = anon_1.id",
                ]
            ),
            id="distinct",
        ),
        pytest.param(
            select(Fruit).join(Fruit.color).where(Fruit.name == "x"),
            snapshot(
                [
                    "SELECT fruit.id",
                    "  FROM fruit AS fruit",
                    "  JOIN (",
                    "        SELECT fruit.id AS id",
                    "          FROM fruit",
                    "          JOIN color",
                    "            ON color.id = fruit.color_id",
                    "         WHERE fruit.name = ?",
                    "       ) AS anon_1",
                    "    ON fruit.id = anon_1.id",
                ]
            ),
            id="join",
        ),
    ],
)
@pytest.mark.inline_snapshot
def test_non_trivial_filter_statement_uses_semijoin(statement: Select[tuple[Fruit]], expected: list[str]) -> None:
    """A non-trivial filter statement (LIMIT/GROUP BY/DISTINCT/JOIN) falls back to the PK semi-join."""
    assert _filter_statement_sql(statement).splitlines() == expected


def test_dedup_columns_collapses_distinct_objects_for_same_column() -> None:
    """Two distinct objects for the same column collapse via structural compare."""
    from sqlalchemy import inspect as sqla_inspect

    fruit = aliased(Fruit)
    attr = fruit.id  # InstrumentedAttribute
    col = sqla_inspect(fruit).selectable.c.id  # distinct Column object for the same column

    result = _dedup_columns([attr, fruit.name, col])  # ty: ignore[invalid-argument-type]

    assert len(result) == 2  # attr and col collapse to one


def test_secondary_aggregation_cte_join_is_bound_by_identity(captured_statements: list[Select[Any]]) -> None:
    """A secondary-table aggregation ON clause references the very objects the join is built on."""
    result = secondary_table_schema.execute_sync(
        "{ users { id departmentsAggregate { count } } }",
        context_value=DialectContext("sqlite"),
    )

    assert not result.errors
    assert len(captured_statements) == 1
    from_elements = captured_statements[0].get_final_froms()
    # An ON clause bound to a name-alike alias object would surface here as an extra FROM element.
    assert len(from_elements) == 1
    join = from_elements[0]
    assert isinstance(join, Join)
    tables = [
        element.table
        for element in visitors.iterate(join.onclause)
        if isinstance(element, ColumnClause) and element.table is not None
    ]
    assert len(tables) == 2
    assert any(table is join.left for table in tables)
    assert any(table.c is join.right.c for table in tables)
