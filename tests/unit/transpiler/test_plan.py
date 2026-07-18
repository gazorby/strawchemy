"""Compile-only, DB-free tests for the QueryPlan IR emitter (QueryPlan.emit)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from inline_snapshot import snapshot
from sqlalchemy import Select, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import aliased, load_only

from strawchemy.transpiler._plan import FilterSemiJoin, HookSpec, QueryPlan
from strawchemy.transpiler._query import HookApplier
from strawchemy.transpiler.hook import QueryHook
from tests.unit.models import Fruit
from tests.utils import format_sql

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass


@dataclass
class _SweetnessFilterHook(QueryHook[Fruit]):
    """Hook that adds a sweetness > 5 WHERE predicate for testing hook replay."""

    def apply_hook(self, statement: Select[Any], alias: AliasedClass[Any]) -> Select[Any]:
        return statement.where(alias.sweetness > 5)


@pytest.mark.inline_snapshot
def test_emit_assembles_select_where_order() -> None:
    """QueryPlan.emit builds SELECT/WHERE/ORDER BY from plan leaf fragments."""
    fruit = aliased(Fruit)
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(load_only(fruit.name),),
        where=(fruit.sweetness > 1,),
        order_by=(fruit.name.asc(),),
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.id",
            "  FROM fruit AS fruit_1",
            " WHERE fruit_1.sweetness > ?",
            " ORDER BY fruit_1.name ASC",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_without_where_or_order() -> None:
    """A plan with no predicates or ordering emits a bare SELECT."""
    fruit = aliased(Fruit)
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(),
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private",
            "  FROM fruit AS fruit_1",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_applies_filter_semijoin() -> None:
    """A filter_semijoin renders as a JOIN on the PK-equality onclause."""
    fruit = aliased(Fruit)
    filter_subquery = select(Fruit.id).subquery().alias()
    semijoin = FilterSemiJoin(
        alias=filter_subquery,  # ty: ignore[invalid-argument-type]
        onclause=fruit.id == filter_subquery.c.id,
    )
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=semijoin,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(),
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private",
            "  FROM fruit AS fruit_1",
            "  JOIN (",
            "        SELECT fruit.id AS id",
            "          FROM fruit",
            "       ) AS anon_1",
            "    ON fruit_1.id = anon_1.id",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_appends_root_aggregation_columns() -> None:
    """Root aggregation function columns are added to the projection."""
    fruit = aliased(Fruit)
    total = func.count().over().label("total_count")
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(),
        root_aggregation_functions=(total,),
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private,",
            "       count(*) OVER () AS total_count",
            "  FROM fruit AS fruit_1",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_applies_limit_and_offset() -> None:
    """limit/offset render on the emitted statement."""
    fruit = aliased(Fruit)
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(),
        limit=5,
        offset=10,
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private",
            "  FROM fruit AS fruit_1",
            " LIMIT ?",
            "OFFSET ?",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_applies_native_distinct_on() -> None:
    """use_distinct_on renders DISTINCT ON and pulls order-by columns into the SELECT list."""
    fruit = aliased(Fruit)
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(fruit.color_id.asc(),),
        distinct_on=(fruit.color_id,),  # ty: ignore[invalid-argument-type]
        use_distinct_on=True,
    )

    assert format_sql(str(plan.emit().compile(dialect=postgresql.dialect()))).splitlines() == snapshot(
        [
            "SELECT DISTINCT",
            "    ON (fruit_1.color_id) fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private",
            "  FROM fruit AS fruit_1",
            " ORDER BY fruit_1.color_id ASC",
        ]
    )


@pytest.mark.inline_snapshot
def test_emit_replays_hook_specs() -> None:
    """QueryPlan.emit replays hook specs via HookApplier, applying apply_hook to the statement.

    A minimal hook subclass that adds sweetness > 5 is registered under a sentinel
    node key. The emitted SQL must contain the WHERE predicate injected by the hook.
    """
    fruit = aliased(Fruit)
    sentinel_node = MagicMock()
    hook = _SweetnessFilterHook()
    hooks: defaultdict[Any, list[QueryHook[Any]]] = defaultdict(list)
    hooks[sentinel_node].append(hook)
    # scope is only accessed for relationship loading; with no relationships configured
    # on the hook, alias_from_relation_node is never called.
    mock_scope = MagicMock()
    applier = HookApplier(scope=mock_scope, hooks=hooks)
    spec = HookSpec(node=sentinel_node, alias=fruit, loading_mode="undefer")  # ty: ignore[invalid-argument-type]
    plan = QueryPlan(
        root=fruit,  # ty: ignore[invalid-argument-type]
        filter_semijoin=None,
        projection_columns=(),
        load_options=(),
        where=(),
        order_by=(),
        hook_specs=(spec,),
        hook_applier=applier,
    )

    assert format_sql(str(plan.emit().compile(dialect=sqlite.dialect()))).splitlines() == snapshot(
        [
            "SELECT fruit_1.name,",
            "       fruit_1.color_id,",
            "       fruit_1.sweetness,",
            "       fruit_1.id,",
            "       fruit_1.private",
            "  FROM fruit AS fruit_1",
            " WHERE fruit_1.sweetness > ?",
        ]
    )


def test_query_plan_emit_is_a_method() -> None:
    """QueryPlan exposes emit() as a method; the free emit_plan is gone."""
    import strawchemy.transpiler._plan as plan_module

    assert hasattr(QueryPlan, "emit")
    assert not hasattr(plan_module, "emit_plan")
