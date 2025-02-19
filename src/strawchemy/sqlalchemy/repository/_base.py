from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from strawchemy.sqlalchemy._transpiler import Transpiler
from strawchemy.sqlalchemy.typing import (
    DeclarativeT,
    QueryExecutorT,
    QueryHookCallableWithoutInfo,
    SessionT,
    SQLAlchemyQueryNode,
)

if TYPE_CHECKING:
    from collections import defaultdict

    from sqlalchemy import Select
    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO


__all__ = ("SQLAlchemyGraphQLRepository",)


T = TypeVar("T", bound=Any)


class SQLAlchemyGraphQLRepository(Generic[DeclarativeT, SessionT]):
    def __init__(
        self,
        model: type[DeclarativeT],
        session: SessionT,
        statement: Select[tuple[DeclarativeT]] | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.session = session
        self.statement = statement
        self.execution_options = execution_options

        self._dialect = session.get_bind().dialect

    def _get_executor(
        self,
        executor_type: type[QueryExecutorT],
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHookCallableWithoutInfo[DeclarativeBase]]]
        | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> QueryExecutorT:
        transpiler = Transpiler(self.model, self._dialect, query_hooks=query_hooks, statement=self.statement)
        return transpiler.executor(
            selection_tree=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            executor_cls=executor_type,
            execution_options=execution_options if execution_options is not None else self.execution_options,
        )
