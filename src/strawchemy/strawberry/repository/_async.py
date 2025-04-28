from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

from strawchemy.sqlalchemy.repository import SQLAlchemyGraphQLAsyncRepository
from strawchemy.strawberry._utils import default_session_getter, dto_model_from_type, strawberry_contained_user_type

from ._base import StrawchemyRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from strawberry import Info
    from strawchemy.graphql.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.input import Input
    from strawchemy.sqlalchemy.typing import AnyAsyncSession
    from strawchemy.strawberry.typing import AsyncSessionGetter, StrawchemyTypeFromPydantic


__all__ = ("StrawchemyAsyncRepository",)

T = TypeVar("T")


@dataclass
class StrawchemyAsyncRepository(StrawchemyRepository[T]):
    type: type[T]
    info: Info[Any, Any]
    root_aggregations: bool = False

    # sqlalchemy related settings
    session_getter: AsyncSessionGetter = default_session_getter
    session: AnyAsyncSession | None = None
    filter_statement: Select[tuple[Any]] | None = None
    execution_options: dict[str, Any] | None = None

    def graphql_repository(self) -> SQLAlchemyGraphQLAsyncRepository[Any]:
        return SQLAlchemyGraphQLAsyncRepository(
            model=dto_model_from_type(strawberry_contained_user_type(self.type)),
            session=self.session or self.session_getter(self.info),
            statement=self.filter_statement,
            execution_options=self.execution_options,
        )

    async def get_one_or_none(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> T | None:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        if result := query_results.one_or_none():
            return self._tree.node_result_to_strawberry_type(result)
        return None

    async def get_one(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> T:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        return self._tree.node_result_to_strawberry_type(query_results.one())

    @overload
    async def get_by_id(self, strict: Literal[True]) -> T: ...

    @overload
    async def get_by_id(self, strict: Literal[False]) -> T | None: ...

    @overload
    async def get_by_id(self, strict: bool = False) -> T | None: ...

    async def get_by_id(self, strict: bool = False, **kwargs: Any) -> T | None:
        query_results = await self.graphql_repository().get_by_id(
            selection=self._tree, query_hooks=self._query_hooks, **kwargs
        )
        result = query_results.one() if strict else query_results.one_or_none()
        return self._tree.node_result_to_strawberry_type(result) if result else None

    async def list(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[T] | T:
        query_results = await self.graphql_repository().list(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        if self.root_aggregations:
            return self._tree.aggregation_query_result_to_strawberry_type(query_results)
        return self._tree.query_result_to_strawberry_type(query_results)

    async def create_many(self, data: Input[Any]) -> Sequence[T]:
        query_results = await self.graphql_repository().create(data, self._tree)
        return self._tree.query_result_to_strawberry_type(query_results)

    async def create(self, data: Input[Any]) -> T:
        query_results = await self.graphql_repository().create(data, self._tree)
        return self._tree.node_result_to_strawberry_type(query_results.one())

    async def update_many_by_id(self, data: Input[Any]) -> Sequence[T]:
        query_results = await self.graphql_repository().update_by_ids(data, self._tree)
        return self._tree.query_result_to_strawberry_type(query_results)

    async def update_by_id(self, data: Input[Any]) -> T:
        query_results = await self.graphql_repository().update_by_ids(data, self._tree)
        return self._tree.node_result_to_strawberry_type(query_results.one())

    async def update_by_filter(
        self, data: Input[Any], filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]]
    ) -> Sequence[T]:
        query_results = await self.graphql_repository().update_by_filter(data, filter_input.to_pydantic(), self._tree)
        return self._tree.query_result_to_strawberry_type(query_results)

    async def delete(
        self, filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None
    ) -> Sequence[T]:
        query_results = await self.graphql_repository().delete(
            self._tree, filter_input.to_pydantic() if filter_input else None
        )
        return self._tree.query_result_to_strawberry_type(query_results)
