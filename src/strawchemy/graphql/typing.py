from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from strawchemy.dto import ModelFieldT, ModelT

    from .dto import (
        AggregateDTO,
        FilterFunctionInfo,
        GraphQLFilterDTO,
        MappedDataclassGraphQLDTO,
        OrderByDTO,
        OutputFunctionInfo,
        UnmappedDataclassGraphQLDTO,
        UnmappedPydanticGraphQLDTO,
    )
    from .filters import NumericComparison

QueryObject = TypeVar("QueryObject", bound=Any)
GraphQLFilterDTOT = TypeVar("GraphQLFilterDTOT", bound="GraphQLFilterDTO[Any]")
AggregateDTOT = TypeVar("AggregateDTOT", bound="AggregateDTO[Any]")
GraphQLDTOT = TypeVar("GraphQLDTOT", bound="GraphQLDTO")
OrderByDTOT = TypeVar("OrderByDTOT", bound="OrderByDTO[Any, Any]")

AggregationFunction = Literal[
    "min", "max", "sum", "avg", "count", "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop"
]
AggregationType = Literal[
    "sum", "numeric", "min_max_datetime", "min_max_date", "min_max_time", "min_max_string", "min_max_numeric"
]

QueryHookCallable: TypeAlias = "Callable[..., Any]"

PydanticGraphQLDTO: TypeAlias = "UnmappedPydanticGraphQLDTO[Any]"
DataclassGraphQLDTO: TypeAlias = "MappedDataclassGraphQLDTO[Any] | UnmappedDataclassGraphQLDTO[Any]"
GraphQLDTO: TypeAlias = "PydanticGraphQLDTO | DataclassGraphQLDTO"
FunctionInfo: TypeAlias = (
    "FilterFunctionInfo[ModelT, ModelFieldT, NumericComparison[Any, Any, Any]] | OutputFunctionInfo"
)
