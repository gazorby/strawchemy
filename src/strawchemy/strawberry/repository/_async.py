from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from strawchemy.sqlalchemy.repository import SQLAlchemyGraphQLAsyncRepository
from strawchemy.strawberry._utils import default_session_getter, dto_model_from_type, strawberry_contained_user_type

from ._base import GraphQLResult, StrawchemyRepository

if TYPE_CHECKING:
    from sqlalchemy import Select
    from strawberry import Info
    from strawchemy.sqlalchemy.typing import AnyAsyncSession
    from strawchemy.strawberry.dto import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.strawberry.mutation.input import Input, InputModel
    from strawchemy.strawberry.typing import AsyncSessionGetter

__all__ = ("StrawchemyAsyncRepository",)

T = TypeVar("T")


@dataclass
class StrawchemyAsyncRepository(StrawchemyRepository[T]):
    type: type[T]
    info: Info[Any, Any]

    # sqlalchemy related settings
    session_getter: AsyncSessionGetter = default_session_getter
    session: AnyAsyncSession | None = None
    filter_statement: Select[tuple[Any]] | None = None
    execution_options: dict[str, Any] | None = None
    deterministic_ordering: bool = False

    def graphql_repository(self) -> SQLAlchemyGraphQLAsyncRepository[Any]:
        return SQLAlchemyGraphQLAsyncRepository(
            model=dto_model_from_type(strawberry_contained_user_type(self.type)),
            session=self.session or self.session_getter(self.info),
            statement=self.filter_statement,
            execution_options=self.execution_options,
            deterministic_ordering=self.deterministic_ordering,
        )

    async def get_one_or_none(
        self,
        filter_input: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> GraphQLResult[Any, T]:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input or None,
            order_by=list(order_by or []),
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        return GraphQLResult(query_results, self._tree)

    async def get_one(
        self,
        filter_input: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> GraphQLResult[Any, T]:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input or None,
            order_by=list(order_by or []),
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        return GraphQLResult(query_results, self._tree)

    async def get_by_id(self, **kwargs: Any) -> GraphQLResult[Any, T]:
        query_results = await self.graphql_repository().get_by_id(
            selection=self._tree, query_hooks=self._query_hooks, **kwargs
        )
        return GraphQLResult(query_results, self._tree)

    async def list(
        self,
        filter_input: BooleanFilterDTO | None = None,
        order_by: list[OrderByDTO] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> GraphQLResult[Any, T]:
        query_results = await self.graphql_repository().list(
            selection=self._tree,
            dto_filter=filter_input or None,
            order_by=list(order_by or []),
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        return GraphQLResult(query_results, self._tree)

    async def create(self, data: Input[InputModel]) -> GraphQLResult[InputModel, T]:
        query_results = await self.graphql_repository().create(data, self._tree)
        return GraphQLResult(query_results, self._tree)

    async def update_by_id(self, data: Input[InputModel]) -> GraphQLResult[InputModel, T]:
        query_results = await self.graphql_repository().update_by_ids(data, self._tree)
        return GraphQLResult(query_results, self._tree)

    async def update_by_filter(
        self, data: Input[InputModel], filter_input: BooleanFilterDTO
    ) -> GraphQLResult[InputModel, T]:
        query_results = await self.graphql_repository().update_by_filter(data, filter_input, self._tree)
        return GraphQLResult(query_results, self._tree)

    async def delete(self, filter_input: BooleanFilterDTO | None) -> GraphQLResult[Any, T]:
        query_results = await self.graphql_repository().delete(self._tree, filter_input or None)
        return GraphQLResult(query_results, self._tree)
