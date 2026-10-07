"""Entry point turning a GraphQL query into a SQLAlchemy statement and its executor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import override

from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.dto.strawberry import GraphQLFieldDefinition
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.repository.typing import DeclarativeT, QueryExecutorT
from strawchemy.transpiler._core.level import Level, PlanContext
from strawchemy.transpiler._core.request import QueryRequest
from strawchemy.transpiler._executor import SyncQueryExecutor
from strawchemy.transpiler._passes import DEFAULT_PIPELINES

if TYPE_CHECKING:
    from collections import defaultdict
    from collections.abc import Sequence

    from sqlalchemy import Dialect
    from sqlalchemy.sql import ColumnElement

    from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import OrderByExpr, QueryNodeType, SelectOf

__all__ = ("Transpiler",)


class Transpiler(Generic[DeclarativeT]):
    """Plans the GraphQL queries of one model into SQLAlchemy statements."""

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: Dialect,
        *,
        statement: SelectOf[DeclarativeT] | None = None,
        query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] | None = None,
        deterministic_ordering: bool = False,
        default_order_by: Sequence[OrderByExpr] | None = None,
    ) -> None:
        """Creates a transpiler whose root rows are restricted by ``statement``, if given.

        ``default_order_by`` applies when the client asks for no ordering; ``deterministic_ordering`` then adds the
        primary keys so that row order is stable.
        """
        self.model = model
        self.context = PlanContext.create(
            model,
            dialect,
            statement=statement,
            query_hooks=query_hooks,
            deterministic_ordering=deterministic_ordering,
            default_order_by=default_order_by,
            pipelines=DEFAULT_PIPELINES,
        )

    def _id_field_definitions(self) -> list[GraphQLFieldDefinition]:
        return [
            GraphQLFieldDefinition.from_field(self.context.inspector.field_definition(pk, DTOConfig(Purpose.READ)))
            for pk in SQLAlchemyInspector.pk_attributes(self.model.__mapper__)
        ]

    def select_executor(
        self,
        selection_tree: QueryNodeType | None = None,
        *,
        dto_filter: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        executor_cls: type[QueryExecutorT] = SyncQueryExecutor,  # ty: ignore[invalid-parameter-default]
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        """Plans the query into one statement and returns an ``executor_cls`` running it."""
        request = QueryRequest(
            self.model,
            selection_tree,
            dto_filter,
            tuple(order_by or ()),
            tuple(distinct_on or ()),
            limit,
            offset,
            allow_null,
        )
        return executor_cls(
            plan=self.context.pipelines.root.plan(Level.root(request, self.context)),
            id_field_definitions=self._id_field_definitions(),
            execution_options=execution_options,
        )

    def filter_expressions(self, dto_filter: BooleanFilterDTO) -> list[ColumnElement[bool]]:
        """Returns the WHERE predicates of ``dto_filter`` on the root model's table, joining no relation."""
        request = QueryRequest(self.model, None, dto_filter, (), (), None, None, False, filter_scope="dml")
        return list(self.context.pipelines.dml.plan(Level.dml(request, self.context)).rows.where)

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.model}>"
