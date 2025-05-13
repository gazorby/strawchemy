from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from .dto import (
        AggregateDTO,
        FilterFunctionInfo,
        GraphQLFilterDTO,
        MappedDataclassGraphQLDTO,
        MappedPydanticGraphQLDTO,
        OrderByDTO,
        OutputFunctionInfo,
        UnmappedDataclassGraphQLDTO,
    )


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
