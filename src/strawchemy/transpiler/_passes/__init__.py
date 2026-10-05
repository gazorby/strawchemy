"""The passes planning each kind of level, and the pipelines wiring them."""

from __future__ import annotations

from strawchemy.transpiler._core.pipeline import Pipeline, Pipelines
from strawchemy.transpiler._passes.aggregations import Aggregations
from strawchemy.transpiler._passes.distinct_on import DistinctOn
from strawchemy.transpiler._passes.filtering import Filtering
from strawchemy.transpiler._passes.ordering import Ordering
from strawchemy.transpiler._passes.pagination import OffsetPagination
from strawchemy.transpiler._passes.query_hooks import QueryHooks
from strawchemy.transpiler._passes.relations import Relations
from strawchemy.transpiler._passes.root_aggregations import RootAggregations
from strawchemy.transpiler._passes.selection import Selection
from strawchemy.transpiler._passes.user_statement import UserStatement

__all__ = ("DEFAULT_PIPELINES",)


DEFAULT_PIPELINES = Pipelines(
    root=Pipeline(
        (
            UserStatement(),
            QueryHooks(),
            Filtering(),
            Ordering(),
            DistinctOn(),
            OffsetPagination(),
            Selection(),
            Relations(),
            Aggregations(),
            RootAggregations(),
        )
    ),
    relation=Pipeline(
        (QueryHooks(), Ordering(), DistinctOn(), OffsetPagination(), Selection(), Relations(), Aggregations())
    ),
    exists=Pipeline((Filtering(),)),
    dml=Pipeline((UserStatement(), Filtering())),
)
