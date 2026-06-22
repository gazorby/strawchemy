"""Tests for the pure planner's frozen result dataclasses."""

from __future__ import annotations

import dataclasses

from strawchemy.transpiler._planner import AggregationPlan, FilterPlan, OrderPlan, ProjectionPlan


def test_pass_dataclasses_are_frozen_with_expected_fields() -> None:
    """Each pass-result dataclass is frozen and exposes exactly its spec fields."""
    for cls in (AggregationPlan, FilterPlan, OrderPlan, ProjectionPlan):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True
    assert {f.name for f in dataclasses.fields(FilterPlan)} == {"where", "joins", "referenced_functions"}
    assert {f.name for f in dataclasses.fields(OrderPlan)} == {"expressions", "joins", "referenced_functions"}
    assert {f.name for f in dataclasses.fields(ProjectionPlan)} == {
        "columns",
        "load_options",
        "aggregation_joins",
        "hook_specs",
        "referenced_functions",
        "transform_map",
    }
    assert {f.name for f in dataclasses.fields(AggregationPlan)} == {"columns", "joins", "aliases", "node_functions"}


def test_pass_dataclasses_construct_with_no_arguments() -> None:
    """Each pass-result dataclass is constructible with zero arguments (empty defaults)."""
    assert AggregationPlan().joins == ()
    assert dict(AggregationPlan().columns) == {}
    assert FilterPlan().where == ()
    assert FilterPlan().referenced_functions == frozenset()
    assert OrderPlan().expressions == ()
    assert OrderPlan().joins == ()
    assert ProjectionPlan().columns == ()
    assert ProjectionPlan().load_options == ()
    assert dict(ProjectionPlan().transform_map) == {}


def test_aggregation_plan_exposes_plan_classmethod() -> None:
    """AggregationPlan.plan is the public entry; the free plan_aggregations is gone."""
    import strawchemy.transpiler._planner as planner

    assert hasattr(AggregationPlan, "plan")
    assert not hasattr(planner, "plan_aggregations")


def test_filter_plan_exposes_plan_classmethod() -> None:
    """FilterPlan.plan is the public entry; the free plan_filter is gone."""
    import strawchemy.transpiler._planner as planner

    assert hasattr(FilterPlan, "plan")
    assert not hasattr(planner, "plan_filter")


def test_order_plan_exposes_plan_classmethod() -> None:
    """OrderPlan.plan is the public entry; the free plan_order is gone."""
    import strawchemy.transpiler._planner as planner

    assert hasattr(OrderPlan, "plan")
    assert not hasattr(planner, "plan_order")


def test_projection_plan_exposes_plan_classmethod() -> None:
    """ProjectionPlan.plan is the public entry; the free plan_projection is gone."""
    import strawchemy.transpiler._planner as planner

    assert hasattr(ProjectionPlan, "plan")
    assert not hasattr(planner, "plan_projection")


def test_composer_phase_helpers_exist() -> None:
    """plan_query/_plan_subquery share FilterPhase/ProjectionPhase extraction helpers."""
    import strawchemy.transpiler._planner as planner

    assert hasattr(planner, "_plan_filter_phase")
    assert hasattr(planner, "_plan_projection_phase")


def test_build_root_aggregations_is_folded_in() -> None:
    """_build_root_aggregations is inlined into _plan_projection_phase; the free helper is gone."""
    import strawchemy.transpiler._planner as planner

    assert not hasattr(planner, "_build_root_aggregations")
    assert hasattr(planner, "_plan_projection_phase")
