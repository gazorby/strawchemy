from __future__ import annotations

from types import UnionType
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeAlias, TypeVar, Union

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql.elements import UnaryExpression
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
        StrawchemyObject,
        UnmappedStrawberryGraphQLDTO,
    )
    from strawchemy.utils.graph import Node
    from strawchemy.validation.pydantic import MappedPydanticGraphQLDTO

__all__ = (
    "UNION_TYPES",
    "AggregateDTOT",
    "AggregationFilterFunction",
    "AggregationFunction",
    "AggregationType",
    "AnyMappedDTO",
    "AnyRepository",
    "AnyRepositoryType",
    "ArrayOperator",
    "ComparisonOperator",
    "CreateOrUpdateResolverResult",
    "DataclassProtocol",
    "DateOperator",
    "DateTimeOperator",
    "EqualityOperator",
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
    "OrderByExpr",
    "OrderOperator",
    "QueryNodeType",
    "QueryObject",
    "StrawberryGraphQLDTO",
    "StrawchemyObjectWithStrawberryObjectDefinition",
    "SupportedDialect",
    "TextOperator",
    "TimeDeltaOperator",
    "TimeOperator",
)

UNION_TYPES = (Union, UnionType)

OrderByExpr: TypeAlias = "UnaryExpression[Any] | InstrumentedAttribute[Any]"


T = TypeVar("T", bound="Any")

QueryObject = TypeVar("QueryObject", bound="Any")
GraphQLFilterDTOT = TypeVar("GraphQLFilterDTOT", bound="GraphQLFilterDTO")
AggregateDTOT = TypeVar("AggregateDTOT", bound="AggregateDTO")
GraphQLDTOT = TypeVar("GraphQLDTOT", bound="GraphQLDTO[Any]")
OrderByDTOT = TypeVar("OrderByDTOT", bound="OrderByDTO")

SupportedDialect: TypeAlias = Literal["postgresql", "mysql", "sqlite"]
"""Must match SQLAlchemy dialect."""

AggregationFunction = Literal["min", "max", "sum", "avg", "count", "stddev_samp", "stddev_pop", "var_samp", "var_pop"]
AggregationFilterFunction: TypeAlias = Union[
    AggregationFunction,
    Literal[
        "min_datetime",
        "max_datetime",
        "min_date",
        "max_date",
        "min_string",
        "max_string",
        "min_time",
        "max_time",
    ],
]
"""Name of a generated aggregation filter field, i.e. ``FilterFunctionInfo.field_name``."""
AggregationType = Literal[
    "sum", "numeric", "min_max_datetime", "min_max_date", "min_max_time", "min_max_string", "min_max_numeric"
]

# Operator vocabularies, one alias per comparison input, composed the way the comparison classes
# themselves compose. Values are the operator's snake_case name; the generated GraphQL field is
# camelCased as usual (``is_null`` becomes ``isNull``).
EqualityOperator: TypeAlias = Literal["eq", "neq", "in", "nin", "is_null"]
"""Operators every comparison input offers."""
OrderOperator: TypeAlias = Union[EqualityOperator, Literal["gt", "gte", "lt", "lte"]]
"""Operators on an orderable column."""
TextOperator: TypeAlias = Union[
    OrderOperator,
    Literal[
        "like",
        "nlike",
        "ilike",
        "nilike",
        "regexp",
        "nregexp",
        "iregexp",
        "inregexp",
        "contains",
        "icontains",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
    ],
]
"""Operators on a text column."""
ArrayOperator: TypeAlias = Union[EqualityOperator, Literal["contains", "contained_in", "overlap"]]
"""Operators on an array column."""
DateOperator: TypeAlias = Union[
    OrderOperator, Literal["year", "quarter", "month", "week", "week_day", "iso_week_day", "iso_year", "day"]
]
"""Operators on a date column, including its extractable parts."""
TimeOperator: TypeAlias = Union[OrderOperator, Literal["hour", "minute", "second"]]
"""Operators on a time column, including its extractable parts."""
DateTimeOperator: TypeAlias = Union[DateOperator, TimeOperator]
"""Operators on a datetime column: every date part and every time part."""
TimeDeltaOperator: TypeAlias = Union[OrderOperator, Literal["days", "hours", "minutes", "seconds"]]
"""Operators on an interval column."""
ComparisonOperator: TypeAlias = Union[TextOperator, ArrayOperator, DateTimeOperator, TimeDeltaOperator]
"""Any operator accepted by ``filter_field(ops=...)``.

Which operators a given field actually accepts depends on the column or aggregation function it
refines; that narrower check happens when the filter class is built. JSON and geo comparisons
declare their operators outside the registry these aliases mirror, so ``ops=`` does not apply to
them.
"""
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
    "Sequence[StrawchemyObjectWithStrawberryObjectDefinition] | StrawchemyObjectWithStrawberryObjectDefinition"
)
ListResolverResult: TypeAlias = OneOrManyResult
GetByIdResolverResult: TypeAlias = "StrawchemyObjectWithStrawberryObjectDefinition | None"
CreateOrUpdateResolverResult: TypeAlias = "OneOrManyResult | ValidationErrorType | Sequence[ValidationErrorType]"


if TYPE_CHECKING:

    class DataclassProtocol(Protocol):
        __dataclass_fields__: ClassVar[dict[str, Any]]

    class StrawchemyObjectWithStrawberryObjectDefinition(StrawchemyObject, WithStrawberryObjectDefinition): ...
