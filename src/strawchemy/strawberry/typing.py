from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Select
    from strawberry import Info
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawchemy.sqlalchemy.typing import AnyAsyncSession, AnySyncSession
    from strawchemy.strawberry.dto import StrawchemyDTOAttributes
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

    from .dto import (
        AggregateDTO,
        FilterFunctionInfo,
        GraphQLFilterDTO,
        MappedDataclassGraphQLDTO,
        OrderByDTO,
        OutputFunctionInfo,
        UnmappedDataclassGraphQLDTO,
    )

__all__ = (
    "AnySessionGetter",
    "AsyncSessionGetter",
    "FilterStatementCallable",
    "StrawchemyTypeFromPydantic",
    "StrawchemyTypeWithStrawberryObjectDefinition",
    "SyncSessionGetter",
)

GraphQLType = Literal["input", "object", "interface", "enum"]
AsyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnyAsyncSession]"
SyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnySyncSession]"
AnySessionGetter: TypeAlias = "AsyncSessionGetter | SyncSessionGetter"
FilterStatementCallable: TypeAlias = "Callable[[Info[Any, Any]], Select[tuple[Any]]]"


T = TypeVar("T")
QueryObject = TypeVar("QueryObject", bound=Any)
GraphQLFilterDTOT = TypeVar("GraphQLFilterDTOT", bound="GraphQLFilterDTO")
AggregateDTOT = TypeVar("AggregateDTOT", bound="AggregateDTO")
GraphQLDTOT = TypeVar("GraphQLDTOT", bound="GraphQLDTO[Any]")
OrderByDTOT = TypeVar("OrderByDTOT", bound="OrderByDTO")

AggregationFunction = Literal["min", "max", "sum", "avg", "count", "stddev_samp", "stddev_pop", "var_samp", "var_pop"]
AggregationType = Literal[
    "sum", "numeric", "min_max_datetime", "min_max_date", "min_max_time", "min_max_string", "min_max_numeric"
]

QueryHookCallable: TypeAlias = "Callable[..., Any]"
InputType = Literal["create", "update_by_pk", "update_by_filter"]
FunctionInfo: TypeAlias = "FilterFunctionInfo | OutputFunctionInfo"

DataclassGraphQLDTO: TypeAlias = "MappedDataclassGraphQLDTO[T] | UnmappedDataclassGraphQLDTO[T]"
GraphQLDTO: TypeAlias = "DataclassGraphQLDTO[T] | MappedPydanticGraphQLDTO[T]"
MappedGraphQLDTO: TypeAlias = "MappedDataclassGraphQLDTO[T] | MappedPydanticGraphQLDTO[T]"
UnmappedGraphQLDTO: TypeAlias = "UnmappedDataclassGraphQLDTO[T]"
AnyMappedDTO: TypeAlias = "MappedDataclassGraphQLDTO[Any] | MappedPydanticGraphQLDTO[Any]"


if TYPE_CHECKING:

    class StrawchemyTypeWithStrawberryObjectDefinition(StrawchemyDTOAttributes, WithStrawberryObjectDefinition): ...

    class StrawchemyTypeFromPydantic(StrawchemyDTOAttributes, StrawberryTypeFromPydantic[PydanticModel]): ...
