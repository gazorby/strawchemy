from __future__ import annotations

from unittest.mock import MagicMock

from strawchemy.dto.strawberry import AggregationFilter, Filter


def _agg(tag: str) -> AggregationFilter:
    """Builds a stand-in AggregationFilter identifiable by ``tag``."""
    agg = MagicMock(spec=AggregationFilter)
    agg.tag = tag
    return agg


def test_iter_aggregation_filters_walks_and_or_not_branches() -> None:
    """iter_aggregation_filters yields every AggregationFilter under and_/or_/not_ in traversal order."""
    inner = Filter(and_=[_agg("a")])
    outer = Filter(and_=[inner, _agg("b")], or_=[Filter(and_=[_agg("c")])], not_=Filter(and_=[_agg("d")]))
    assert [aggregation_filter.tag for aggregation_filter in outer.iter_aggregation_filters()] == ["a", "b", "c", "d"]  # ty:ignore[unresolved-attribute]
