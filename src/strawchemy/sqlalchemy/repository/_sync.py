# Do not edit this file directly. It has been autogenerated from
# src/strawchemy/sqlalchemy/repository/_async.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from strawchemy.sqlalchemy._executor import QueryResult, SyncQueryExecutor
from strawchemy.sqlalchemy.typing import (
    AnySyncSession,
    DeclarativeT,
    QueryHookCallableWithoutInfo,
    SQLAlchemyQueryNode,
)

from ._base import SQLAlchemyGraphQLRepository

if TYPE_CHECKING:
    from collections import defaultdict

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO


__all__ = ()

T = TypeVar("T", bound=Any)


class SQLAlchemyGraphQLSyncRepository(SQLAlchemyGraphQLRepository[DeclarativeT, AnySyncSession]):
    def list(
        self,
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
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            executor_type=SyncQueryExecutor,
            selection=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            query_hooks=query_hooks,
            execution_options=execution_options,
        )
        return executor.list(self.session)

    def get_one(
        self,
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
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            executor_type=SyncQueryExecutor,
            selection=selection,
            dto_filter=dto_filter,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct_on=distinct_on,
            allow_null=allow_null,
            query_hooks=query_hooks,
            execution_options=execution_options,
            **kwargs,
        )
        return executor.get_one_or_none(self.session)

    def get_by_id(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHookCallableWithoutInfo[DeclarativeBase]]]
        | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            SyncQueryExecutor, selection=selection, query_hooks=query_hooks, execution_options=execution_options
        )
        executor.base_statement = executor.base_statement.where(
            *[
                field_def.model_field == kwargs.pop(field_def.name)
                for field_def in executor.scope.id_field_definitions(self.model)
            ]
        )
        return executor.get_one_or_none(self.session)
