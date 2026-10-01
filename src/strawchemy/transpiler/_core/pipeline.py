"""Passes and the pipeline loop that runs them over one level: every rows stage, then every projection stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from strawchemy.exceptions import TranspilingError
from strawchemy.transpiler._core.rowset import Projection, RowSet

if TYPE_CHECKING:
    from strawchemy.transpiler._core.level import Level
    from strawchemy.transpiler._core.plan import QueryPlan

__all__ = ("Pass", "PassBase", "Pipeline", "Pipelines")


class Pass(Protocol):
    """One capability, split into what it does to the selected rows and to what is read from them."""

    def rows(self, level: Level, rows: RowSet) -> RowSet: ...

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        """Adds to ``projection``; ``rows`` is the finished RowSet, whose joins it may reuse but never change."""
        ...


class PassBase:
    """A pass that changes nothing, to subclass when overriding a single stage."""

    def rows(self, level: Level, rows: RowSet) -> RowSet:
        return rows

    def project(self, level: Level, rows: RowSet, projection: Projection) -> Projection:
        return projection


@dataclass(frozen=True)
class Pipeline:
    """The passes planning one kind of level; their order carries no meaning."""

    passes: tuple[Pass, ...]

    def __post_init__(self) -> None:
        """Rejects a pipeline holding two passes of one type.

        Raises:
            TranspilingError: If two passes share a type.
        """
        seen: set[type[Pass]] = set()
        for pass_ in self.passes:
            if (pass_type := type(pass_)) in seen:
                msg = f"Pipeline has two passes of type {pass_type.__name__}"
                raise TranspilingError(msg)
            seen.add(pass_type)

    def plan(self, level: Level) -> QueryPlan:
        rows = RowSet.over(level.alias)
        for pass_ in self.passes:
            rows = pass_.rows(level, rows)

        projection = Projection.over(level.node, level.alias)
        for pass_ in self.passes:
            projection = pass_.project(level, rows, projection)

        return level.materialize(rows, projection)

    def replace(self, old: type[Pass], new: Pass) -> Pipeline:
        """Returns a pipeline with ``new`` in place of the pass of type ``old``."""
        return Pipeline(tuple(new if type(pass_) is old else pass_ for pass_ in self.passes))


@dataclass(frozen=True)
class Pipelines:
    root: Pipeline
    relation: Pipeline
    exists: Pipeline
    dml: Pipeline
