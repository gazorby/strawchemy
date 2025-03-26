from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import insert
from sqlalchemy.orm import NO_VALUE
from sqlalchemy.orm.util import object_state
from strawchemy.sqlalchemy._executor import AsyncQueryExecutor, QueryResult
from strawchemy.sqlalchemy.typing import AnyAsyncSession, DeclarativeT, SQLAlchemyQueryNode

from ._base import SQLAlchemyGraphQLRepository

if TYPE_CHECKING:
    from collections import defaultdict
    from collections.abc import Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.graphql.typing import AnyMappedDTO
    from strawchemy.sqlalchemy.hook import QueryHook


__all__ = ("SQLAlchemyGraphQLAsyncRepository",)

T = TypeVar("T", bound=Any)


class SQLAlchemyGraphQLAsyncRepository(SQLAlchemyGraphQLRepository[DeclarativeT, AnyAsyncSession]):
    async def list(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            executor_type=AsyncQueryExecutor,
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
        return await executor.list(self.session)

    async def get_one(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct_on: list[EnumDTO] | None = None,
        allow_null: bool = False,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            executor_type=AsyncQueryExecutor,
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
        return await executor.get_one_or_none(self.session)

    async def get_by_id(
        self,
        selection: SQLAlchemyQueryNode | None = None,
        query_hooks: defaultdict[SQLAlchemyQueryNode, list[QueryHook[DeclarativeBase]]] | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> QueryResult[DeclarativeT]:
        executor = self._get_executor(
            AsyncQueryExecutor, selection=selection, query_hooks=query_hooks, execution_options=execution_options
        )
        executor.base_statement = executor.base_statement.where(
            *[
                field_def.model_field == kwargs.pop(field_def.name)
                for field_def in executor.scope.id_field_definitions(self.model)
            ]
        )
        return await executor.get_one_or_none(self.session)

    async def create_many(self, data: Sequence[AnyMappedDTO]) -> QueryResult[DeclarativeT]:
        use_insert = True
        relationship_keys = {relationship.key for relationship in self.model.__mapper__.relationships}
        instances: Sequence[DeclarativeT] = []
        for dto in data:
            instance = dto.to_mapped()
            instances.append(instance)
            loaded_keys = {attr.key for attr in object_state(instance).attrs if attr.loaded_value is not NO_VALUE}
            if loaded_keys & relationship_keys:
                use_insert = False
                break
        if use_insert:
            values: list[dict[str, Any]] = []
            for dto, instance in zip(data, instances, strict=True):
                include = {field.model_field_name for field in dto.__dto_field_definitions__.values()}
                exclude = object_state(instance).unloaded
                values.append(
                    {
                        field: getattr(instance, field)
                        for field in instance.__mapper__.columns.keys()  # noqa: SIM118
                        if field not in exclude and field in include
                    }
                )

            result = await self.session.scalars(
                insert(self.model).returning(self.model, sort_by_parameter_order=True), values
            )
            instances = result.all()
        else:
            self.session.add_all(data)
            await self.session.commit()

        return QueryResult(nodes=instances)
