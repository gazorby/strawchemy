"""The immutable ``QueryPlan`` a level produces, and ``emit`` which renders it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from strawchemy.exceptions import TranspilingError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy import Label, Select
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement

    from strawchemy.transpiler._core.level import PlanContext
    from strawchemy.transpiler._core.rowset import AliasPage, Join, Projection, RowSet
    from strawchemy.typing import QueryNodeType

__all__ = ("QueryPlan",)


@dataclass(frozen=True)
class QueryPlan:
    rows: RowSet
    projection: Projection
    context: PlanContext
    join_to_parent: Join | None = None

    @property
    def column_map(self) -> Mapping[QueryNodeType, ColumnElement[Any]]:
        return self.projection.column_map

    @property
    def identity_columns(self) -> Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]]:
        return self.projection.identity_columns

    @property
    def root_entity(self) -> AliasedClass[Any]:
        """The entity of the root rows, the first of the projection.

        Raises:
            TranspilingError: If the projection has no entity.
        """
        if (entity := next(iter(self.projection.entities.values()), None)) is None:
            msg = "the plan projects no entity"
            raise TranspilingError(msg)
        return entity

    @property
    def relation_entities(self) -> Mapping[QueryNodeType, AliasedClass[Any]]:
        root = next(iter(self.projection.entities), None)
        return {node: alias for node, alias in self.projection.entities.items() if node is not root}

    @property
    def relation_pages(self) -> Mapping[QueryNodeType, AliasPage]:
        return self.projection.pages

    @property
    def root_aggregation_functions(self) -> tuple[Label[Any], ...]:
        return self.projection.root_aggregations

    def emit(self) -> Select[Any]:
        from strawchemy.transpiler._core.render import render_plan  # noqa: PLC0415

        return render_plan(self)
