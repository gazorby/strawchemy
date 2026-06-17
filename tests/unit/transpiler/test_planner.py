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
