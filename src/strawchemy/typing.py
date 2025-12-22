from __future__ import annotations

from types import UnionType
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeAlias, TypeVar, Union

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Select
    from strawberry import Info
    from strawberry.types.base import WithStrawberryObjectDefinition

    from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository, ValidationErrorType
    from strawchemy.dto.strawberry import (
        AggregateDTO,
        FilterFunctionInfo,
        GraphQLFieldDefinition,
        GraphQLFilterDTO,
        MappedStrawberryGraphQLDTO,
        OrderByDTO,
        OutputFunctionInfo,
        QueryNodeMetadata,
        StrawchemyDTOAttributes,
        UnmappedStrawberryGraphQLDTO,
    )
    from strawchemy.utils.graph import Node
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

__all__ = (
    "UNION_TYPES",
    "AggregateDTOT",
    "AggregationFunction",
    "AggregationType",
    "AnyMappedDTO",
    "AnyRepository",
    "AnyRepositoryType",
    "CreateOrUpdateResolverResult",
    "DataclassProtocol",
    "FilterStatementCallable",
    "FunctionInfo",
    "GetByIdResolverResult",
    "GraphQLDTO",
    "GraphQLDTOT",
    "GraphQLFilterDTOT",
    "GraphQLPurpose",
    "GraphQLType",
    "ListResolverResult",
    "MappedGraphQLDTO",
    "OneOrManyResult",
    "OrderByDTOT",
    "QueryNodeType",
    "QueryObject",
    "StrawberryGraphQLDTO",
    "StrawchemyTypeWithStrawberryObjectDefinition",
    "SupportedDialect",
)

UNION_TYPES = (Union, UnionType)


T = TypeVar("T", bound="Any")

QueryObject = TypeVar("QueryObject", bound="Any")
GraphQLFilterDTOT = TypeVar("GraphQLFilterDTOT", bound="GraphQLFilterDTO")
AggregateDTOT = TypeVar("AggregateDTOT", bound="AggregateDTO")
GraphQLDTOT = TypeVar("GraphQLDTOT", bound="GraphQLDTO[Any]")
OrderByDTOT = TypeVar("OrderByDTOT", bound="OrderByDTO")

SupportedDialect: TypeAlias = Literal["postgresql", "mysql", "sqlite"]
"""Must match SQLAlchemy dialect."""

AggregationFunction = Literal["min", "max", "sum", "avg", "count", "stddev_samp", "stddev_pop", "var_samp", "var_pop"]
AggregationType = Literal[
    "sum", "numeric", "min_max_datetime", "min_max_date", "min_max_time", "min_max_string", "min_max_numeric"
]
GraphQLType = Literal["input", "object", "interface", "enum"]

AnyRepository: TypeAlias = "StrawchemySyncRepository[Any] | StrawchemyAsyncRepository[Any]"
AnyRepositoryType: TypeAlias = "type[AnyRepository]"
FilterStatementCallable: TypeAlias = "Callable[[Info[Any, Any]], Select[tuple[Any]]]"
GraphQLPurpose: TypeAlias = Literal[
    "type",
    "aggregate_type",
    "create_input",
    "update_by_pk_input",
    "update_by_filter_input",
    "filter",
    "aggregate_filter",
    "order_by",
    "upsert_update_fields",
    "upsert_conflict_fields",
]
FunctionInfo: TypeAlias = "FilterFunctionInfo | OutputFunctionInfo"
StrawberryGraphQLDTO: TypeAlias = "MappedStrawberryGraphQLDTO[T] | UnmappedStrawberryGraphQLDTO[T]"
GraphQLDTO: TypeAlias = "StrawberryGraphQLDTO[T] | MappedPydanticGraphQLDTO[T]"
MappedGraphQLDTO: TypeAlias = "MappedStrawberryGraphQLDTO[T] | MappedPydanticGraphQLDTO[T]"
AnyMappedDTO: TypeAlias = "MappedStrawberryGraphQLDTO[Any] | MappedPydanticGraphQLDTO[Any]"
QueryNodeType: TypeAlias = "Node[GraphQLFieldDefinition, QueryNodeMetadata]"
OneOrManyResult: TypeAlias = (
    "Sequence[StrawchemyTypeWithStrawberryObjectDefinition] | StrawchemyTypeWithStrawberryObjectDefinition"
)
ListResolverResult: TypeAlias = OneOrManyResult
GetByIdResolverResult: TypeAlias = "StrawchemyTypeWithStrawberryObjectDefinition | None"
CreateOrUpdateResolverResult: TypeAlias = "OneOrManyResult | ValidationErrorType | Sequence[ValidationErrorType]"


if TYPE_CHECKING:

    class DataclassProtocol(Protocol):
        __dataclass_fields__: ClassVar[dict[str, Any]]

    class StrawchemyTypeWithStrawberryObjectDefinition(StrawchemyDTOAttributes, WithStrawberryObjectDefinition): ...
