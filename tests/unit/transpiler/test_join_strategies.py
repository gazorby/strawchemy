"""Tests for join strategy selection and construction."""

from __future__ import annotations

from strawchemy.config.databases import DatabaseFeatures
from strawchemy.transpiler._strategies import (
    CteJoinStrategy,
    LateralJoinStrategy,
    select_join_strategy,
)


def test_select_join_strategy_returns_lateral_when_supported() -> None:
    """A lateral-capable dialect selects the lateral strategy."""
    db_features = DatabaseFeatures.new("postgresql")
    assert db_features.supports_lateral is True
    strategy = select_join_strategy(db_features)
    assert isinstance(strategy, LateralJoinStrategy)
    assert callable(strategy.relation_join)


def test_select_join_strategy_returns_cte_when_not_supported() -> None:
    """A dialect without lateral selects the CTE strategy."""
    db_features = DatabaseFeatures.new("sqlite")
    assert db_features.supports_lateral is False
    strategy = select_join_strategy(db_features)
    assert isinstance(strategy, CteJoinStrategy)
    assert callable(strategy.relation_join)
