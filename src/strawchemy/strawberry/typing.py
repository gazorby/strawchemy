from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Select
    from strawberry import Info
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawchemy.graph import Node
    from strawchemy.sqlalchemy.typing import AnyAsyncSession, AnySyncSession
    from strawchemy.strawberry.dto import GraphQLFieldDefinition, QueryNodeMetadata, StrawchemyDTOAttributes
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

    from .dto import (
        AggregateDTO,
        FilterFunctionInfo,
        GraphQLFilterDTO,
        MappedStrawberryGraphQLDTO,
        OrderByDTO,
        OutputFunctionInfo,
        UnmappedStrawberryGraphQLDTO,
    )

__all__ = (
    "AnySessionGetter",
    "AsyncSessionGetter",
    "FilterStatementCallable",
    "StrawchemyTypeWithStrawberryObjectDefinition",
    "SyncSessionGetter",
)


_T = TypeVar("_T")
QueryObject = TypeVar("QueryObject", bound="Any")
GraphQLFilterDTOT = TypeVar("GraphQLFilterDTOT", bound="GraphQLFilterDTO")
AggregateDTOT = TypeVar("AggregateDTOT", bound="AggregateDTO")
GraphQLDTOT = TypeVar("GraphQLDTOT", bound="GraphQLDTO[Any]")
OrderByDTOT = TypeVar("OrderByDTOT", bound="OrderByDTO")

AggregationFunction = Literal["min", "max", "sum", "avg", "count", "stddev_samp", "stddev_pop", "var_samp", "var_pop"]
AggregationType = Literal[
    "sum", "numeric", "min_max_datetime", "min_max_date", "min_max_time", "min_max_string", "min_max_numeric"
]

GraphQLType = Literal["input", "object", "interface", "enum"]
AsyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnyAsyncSession]"
SyncSessionGetter: TypeAlias = "Callable[[Info[Any, Any]], AnySyncSession]"
AnySessionGetter: TypeAlias = "AsyncSessionGetter | SyncSessionGetter"
FilterStatementCallable: TypeAlias = "Callable[[Info[Any, Any]], Select[tuple[Any]]]"
InputType = Literal["create", "update_by_pk", "update_by_filter"]
FunctionInfo: TypeAlias = "FilterFunctionInfo | OutputFunctionInfo"
StrawberryGraphQLDTO: TypeAlias = "MappedStrawberryGraphQLDTO[_T] | UnmappedStrawberryGraphQLDTO[_T]"
GraphQLDTO: TypeAlias = "StrawberryGraphQLDTO[_T] | MappedPydanticGraphQLDTO[_T]"
MappedGraphQLDTO: TypeAlias = "MappedStrawberryGraphQLDTO[_T] | MappedPydanticGraphQLDTO[_T]"
AnyMappedDTO: TypeAlias = "MappedStrawberryGraphQLDTO[Any] | MappedPydanticGraphQLDTO[Any]"
QueryNodeType: TypeAlias = "Node[GraphQLFieldDefinition, QueryNodeMetadata]"

if TYPE_CHECKING:

    class StrawchemyTypeWithStrawberryObjectDefinition(StrawchemyDTOAttributes, WithStrawberryObjectDefinition): ...
