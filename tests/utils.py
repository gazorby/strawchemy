from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast, overload, override

from strawchemy.dto.backend.dataclass import DataclassDTOBackend, MappedDataclassDTO
from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTOBackend
from strawchemy.dto.base import DTOFactory
from strawchemy.sqlalchemy.inspector import SQLAlchemyInspector

import strawberry
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.types.execution import ExecutionResult
from tests.typing import AnyFactory, MappedDataclassFactory, MappedPydanticFactory

if TYPE_CHECKING:
    from collections.abc import Awaitable, Generator

    from strawchemy.sqlalchemy.typing import AnySession
    from strawchemy.typing import DataclassProtocol

    from sqlalchemy.orm import Session

    from .typing import AnyQueryExecutor, AsyncQueryExecutor, SyncQueryExecutor

__all__ = ("DTOInspect", "generate_query", "sqlalchemy_dataclass_factory", "sqlalchemy_pydantic_factory")


T = TypeVar("T")


def sqlalchemy_dataclass_factory() -> MappedDataclassFactory:
    return DTOFactory(SQLAlchemyInspector(), DataclassDTOBackend(MappedDataclassDTO))


def sqlalchemy_pydantic_factory() -> MappedPydanticFactory:
    return DTOFactory(SQLAlchemyInspector(), PydanticDTOBackend(MappedPydanticDTO))


def factory_iterator() -> Generator[AnyFactory]:
    for factory in (sqlalchemy_dataclass_factory, sqlalchemy_pydantic_factory):
        yield factory()


@overload
def generate_query(
    session: Session,
    query: type[Any] | None = None,
    mutation: type[Any] | None = None,
    scalar_overrides: dict[object, Any] | None = None,
) -> SyncQueryExecutor: ...


@overload
def generate_query(
    session: AsyncSession,
    query: type[Any] | None = None,
    mutation: type[Any] | None = None,
    scalar_overrides: dict[object, Any] | None = None,
) -> AsyncQueryExecutor: ...


@overload
def generate_query(
    session: Session | None = None,
    query: type[Any] | None = None,
    mutation: type[Any] | None = None,
    scalar_overrides: dict[object, Any] | None = None,
) -> SyncQueryExecutor: ...


def generate_query(
    session: AnySession | None = None,
    query: type[Any] | None = None,
    mutation: type[Any] | None = None,
    scalar_overrides: dict[object, Any] | None = None,
) -> AnyQueryExecutor:
    append_mutation = mutation and not query
    if query is None:

        @strawberry.type
        class Query:
            x: int

        query = Query
    extensions = []
    schema = strawberry.Schema(query=query, mutation=mutation, extensions=extensions, scalar_overrides=scalar_overrides)
    context = None if session is None else StrawberryContext(session)

    def process_result(result: ExecutionResult) -> ExecutionResult:
        return result

    async def query_async(query: str, variable_values: dict[str, Any] | None = None) -> ExecutionResult:
        if append_mutation and not query.startswith("mutation"):
            query = f"mutation {query}"
        result = await schema.execute(query, variable_values=variable_values, context_value=context)
        return process_result(result)

    def query_sync(query: str, variable_values: dict[str, Any] | None = None) -> ExecutionResult:
        if append_mutation and not query.startswith("mutation"):
            query = f"mutation {query}"

        result = schema.execute_sync(query, variable_values=variable_values, context_value=context)
        return process_result(result)

    if isinstance(session, AsyncSession):
        return query_async

    return query_sync


@overload
async def maybe_async(obj: Awaitable[T] | T) -> T: ...


@overload
async def maybe_async(obj: Awaitable[T]) -> T: ...


@overload
async def maybe_async(obj: T) -> T: ...


async def maybe_async(obj: Awaitable[T] | T) -> T:
    return cast(T, await obj) if inspect.isawaitable(obj) else cast(T, obj)


@dataclass
class StrawberryContext:
    session: AnySession


class FactoryType(Enum):
    PYDANTIC = auto()
    DATACLASS = auto()


class DTOInspectProtocol(Protocol):
    @classmethod
    def is_class(cls, dto: type[Any]) -> bool: ...

    def has_init_arg(self, dto: type[Any], name: str) -> bool: ...


class DataclassInspect(DTOInspectProtocol):
    @classmethod
    @override
    def is_class(cls, dto: type[Any]) -> bool:
        return dataclasses.is_dataclass(dto)

    @override
    def has_init_arg(self, dto: type[DataclassProtocol], name: str) -> bool:
        return name in {field.name for field in dataclasses.fields(dto) if field.init}


class PydanticInspect(DTOInspectProtocol):
    @classmethod
    @override
    def is_class(cls, dto: type[Any]) -> bool:
        return issubclass(dto, BaseModel)

    @override
    def has_init_arg(self, dto: type[BaseModel], name: str) -> bool:
        return bool((field := dto.model_fields.get(name)) and field.is_required())


@dataclass
class DTOInspect:
    dto: type[Any]
    inspectors: list[type[DTOInspectProtocol]] = dataclasses.field(
        default_factory=lambda: [DataclassInspect, PydanticInspect]
    )
    inspect: DTOInspectProtocol = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        for inspector in self.inspectors:
            if inspector.is_class(self.dto):
                self.inspect = inspector()
                break
        else:
            msg = f"Unknown dto type: {self.dto}"
            raise TypeError(msg)

    def has_init_arg(self, name: str) -> bool:
        return self.inspect.has_init_arg(self.dto, name)
