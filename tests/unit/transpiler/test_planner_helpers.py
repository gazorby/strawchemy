"""DB-free tests for the pure planner helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import aliased

from strawchemy.transpiler._planner import UserStatementPlan, _dedup_columns, _use_distinct_rank
from tests.unit.models import Fruit


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


# ---------------------------------------------------------------------------
# UserStatementPlan tests (Task 3)
# ---------------------------------------------------------------------------


def _statement_plan(statement: object) -> UserStatementPlan:
    """Builds a UserStatementPlan over the Fruit model with a stand-in scope.

    is_trivial/inline_where only read aliases.model, so a SimpleNamespace suffices here;
    the semijoin path is exercised by the integration tests.
    """
    return UserStatementPlan(statement=statement, aliases=SimpleNamespace(model=Fruit))  # ty: ignore[invalid-argument-type]


def test_user_statement_plan_trivial_for_plain_where_select() -> None:
    """A WHERE-only select of the root model is trivial."""
    assert _statement_plan(select(Fruit).where(Fruit.name == "x")).is_trivial() is True


def test_user_statement_plan_not_trivial_with_limit() -> None:
    """A select carrying LIMIT is not trivial."""
    assert _statement_plan(select(Fruit).where(Fruit.name == "x").limit(5)).is_trivial() is False


def test_user_statement_plan_not_trivial_with_group_by() -> None:
    """A select carrying GROUP BY is not trivial."""
    assert _statement_plan(select(Fruit).where(Fruit.name == "x").group_by(Fruit.color_id)).is_trivial() is False


def test_user_statement_plan_not_trivial_with_distinct() -> None:
    """A select carrying DISTINCT is not trivial."""
    assert _statement_plan(select(Fruit).where(Fruit.name == "x").distinct()).is_trivial() is False


def test_user_statement_plan_not_trivial_with_join() -> None:
    """A select carrying a join is not trivial."""
    assert _statement_plan(select(Fruit).join(Fruit.color).where(Fruit.name == "x")).is_trivial() is False


def test_user_statement_plan_inline_where_adapts_to_alias() -> None:
    """The inlined WHERE returns a single non-None clause bound to the alias."""
    root_alias = aliased(Fruit, name="fruit")
    predicate = _statement_plan(select(Fruit).where(Fruit.name == "x")).inline_where(root_alias)  # ty: ignore[invalid-argument-type]
    assert predicate is not None
    compiled = str(predicate.compile(dialect=sqlite.dialect()))
    assert "name" in compiled


def test_user_statement_plan_apply_to_statement_inlines_trivial() -> None:
    """apply_to_statement inlines a trivial statement's WHERE without a join."""
    root_alias = aliased(Fruit, name="fruit")
    base = select(root_alias)
    result = _statement_plan(select(Fruit).where(Fruit.name == "x")).apply_to_statement(base, root_alias)  # ty: ignore[invalid-argument-type]
    compiled = str(result.compile(dialect=sqlite.dialect()))
    assert "WHERE" in compiled
    assert "JOIN" not in compiled


def test_dedup_columns_collapses_distinct_objects_for_same_column() -> None:
    """Two distinct objects for the same column collapse via structural compare."""
    from sqlalchemy import inspect as sqla_inspect

    fruit = aliased(Fruit)
    attr = fruit.id  # InstrumentedAttribute
    col = sqla_inspect(fruit).selectable.c.id  # distinct Column object for the same column

    result = _dedup_columns([attr, fruit.name, col])  # ty: ignore[invalid-argument-type]

    assert len(result) == 2  # attr and col collapse to one
