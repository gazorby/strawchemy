"""GraphQL filter definitions for DTOs.

This module defines classes and type aliases for creating GraphQL filters
used in data transfer objects (DTOs). It includes comparison classes for
various data types, such as numeric, text, JSONB, arrays, dates, times,
and geometries. These classes allow for building boolean expressions to
compare fields of DTOs in GraphQL queries.
"""

# ruff: noqa: TC003, TC002, TC001
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Generic, TypeAlias, TypeVar, override

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PrivateAttr

from strawchemy.dto.base import ModelFieldT, ModelT

if TYPE_CHECKING:
    from strawchemy.graphql.dto import OrderByEnum, QueryNode

__all__ = (
    "DateComparison",
    "GenericComparison",
    "GraphQLComparison",
    "JSONComparison",
    "OrderComparison",
    "PostgresArrayComparison",
    "TextComparison",
    "TimeComparison",
    "TimeDeltaComparison",
)

T = TypeVar("T")
AnyGraphQLComparison = TypeVar("AnyGraphQLComparison", bound="GraphQLComparison[Any, Any]")
AnyOrderComparison = TypeVar("AnyOrderComparison", bound="OrderComparison[Any, Any, Any]")
GraphQLFilter: TypeAlias = "GraphQLComparison[ModelT, ModelFieldT] | OrderByEnum"


def _valid_regex(string: str) -> str:
    try:
        re.compile(string)
    except re.error as error:
        msg = f"Invalid regular expression: '{string}'"
        raise ValueError(msg) from error
    else:
        return string


def _normalize_field_name(type_: type[Any]) -> str:
    name = type_.__name__
    if name.isupper():
        return name
    name = name.capitalize()
    if name == "Bool":
        return "Boolean"
    if name == "Str":
        return "String"
    return name


RegexPatternStr = Annotated[str, AfterValidator(_valid_regex)]


class GraphQLComparison(BaseModel, Generic[ModelT, ModelFieldT]):
    """Base class for GraphQL comparison filters.

    This class provides a foundation for creating comparison filters
    that can be used in GraphQL queries. It defines the basic structure
    and methods for comparing fields of a specific type.

    Attributes:
        _description: A class variable that stores the description of the
            comparison.
        _field_node: A private attribute that stores the DTO field node.
    """

    model_config = ConfigDict(populate_by_name=True)

    _description: ClassVar[str] = (
        "Boolean expression to compare fields of type {field}. All fields are combined with logical 'AND'"
    )
    _field_node: QueryNode[ModelT, Any] | None = PrivateAttr(default=None)

    def to_expressions(self, dialect: Any, model_attribute: Any) -> Any:
        raise NotImplementedError

    @classmethod
    def comparison_type_name(cls) -> str:
        try:
            prefix = cls.compared_type_name()
        except NotImplementedError:
            prefix = cls.__name__

        return f"{prefix}Comparison"

    @classmethod
    def compared_type_name(cls) -> str:
        raise NotImplementedError

    @classmethod
    def field_description(cls) -> str:
        return cls._description.format(field=cls.compared_type_name())

    @property
    def field_node(self) -> QueryNode[ModelT, ModelFieldT]:
        if self._field_node is None:
            raise ValueError
        return self._field_node

    @field_node.setter
    def field_node(self, value: QueryNode[ModelT, ModelFieldT]) -> None:
        self._field_node = value


class GenericComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[T, ModelT, ModelFieldT]):
    """Generic comparison class for GraphQL filters.

    This class provides a set of generic comparison operators that can be
    used to filter data based on equality, inequality, null checks, and
    inclusion in a list.

    Attributes:
        eq: Filters for values equal to this.
        neq: Filters for values not equal to this.
        is_null: Filters for null values if True, or non-null values if False.
        in: Filters for values present in this list.
        nin: Filters for values not present in this list.
    """

    eq: T | None = None
    neq: T | None = None
    is_null: bool | None = None
    in_: list[T] | None = Field(alias="in", default=None)
    nin: list[T] | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        type_: type[Any] = cls.__pydantic_generic_metadata__["args"][0]
        return _normalize_field_name(type_)


class OrderComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[T, ModelT, ModelFieldT]):
    """Order comparison class for GraphQL filters.

    This class provides a set of numeric comparison operators that can be
    used to filter data based on greater than, less than, and equality.

    Attributes:
        gt: Filters for values greater than this.
        gte: Filters for values greater than or equal to this.
        lt: Filters for values less than this.
        lte: Filters for values less than or equal to this.
    """

    gt: T | None = None
    gte: T | None = None
    lt: T | None = None
    lte: T | None = None


class TextComparison(GraphQLComparison[ModelT, ModelFieldT]):
    """Text comparison class for GraphQL filters.

    This class provides a set of text comparison operators that can be
    used to filter data based on various string matching patterns.

    Attributes:
        like: Filters for values that match this SQL LIKE pattern.
        nlike: Filters for values that do not match this SQL LIKE pattern.
        ilike: Filters for values that match this case-insensitive SQL LIKE pattern.
        nilike: Filters for values that do not match this case-insensitive SQL LIKE pattern.
        regexp: Filters for values that match this regular expression.
        nregexp: Filters for values that do not match this regular expression.
        startswith: Filters for values that start with this string.
        endswith: Filters for values that end with this string.
        contains: Filters for values that contain this string.
        istartswith: Filters for values that start with this string (case-insensitive).
        iendswith: Filters for values that end with this string (case-insensitive).
        icontains: Filters for values that contain this string (case-insensitive).
    """

    like: str | None = None
    nlike: str | None = None
    ilike: str | None = None
    nilike: str | None = None
    regexp: RegexPatternStr | None = None
    iregexp: RegexPatternStr | None = None
    nregexp: RegexPatternStr | None = None
    inregexp: RegexPatternStr | None = None
    startswith: str | None = None
    endswith: str | None = None
    contains: str | None = None
    istartswith: str | None = None
    iendswith: str | None = None
    icontains: str | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "String"


class JSONComparison(GraphQLComparison[ModelT, ModelFieldT]):
    """JSON comparison class for GraphQL filters.

    This class provides a set of JSON comparison operators that can be
    used to filter data based on containment, key existence, and other
    JSON-specific properties.

    Attributes:
        contains: Filters for JSON values that contain this JSON object.
        contained_in: Filters for JSON values that are contained in this JSON object.
        has_key: Filters for JSON values that have this key.
        has_key_all: Filters for JSON values that have all of these keys.
        has_key_any: Filters for JSON values that have any of these keys.
    """

    contains: dict[str, Any] | None = None
    contained_in: dict[str, Any] | None = None
    has_key: str | None = None
    has_key_all: list[str] | None = None
    has_key_any: list[str] | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "JSON"


class PostgresArrayComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[T, ModelT, ModelFieldT]):
    """Postgres array comparison class for GraphQL filters.

    This class provides a set of array comparison operators that can be
    used to filter data based on containment, overlap, and other
    array-specific properties.

    Attributes:
        contains: Filters for array values that contain all elements in this list.
        contained_in: Filters for array values that are contained in this list.
        overlap: Filters for array values that have any elements in common with this list.
    """

    _description: ClassVar[str] = (
        "Boolean expression to compare array fields of type {field}. All fields are combined with logical 'AND'"
    )

    contains: list[T] | None = None
    contained_in: list[T] | None = None
    overlap: list[T] | None = None

    @override
    @classmethod
    def comparison_type_name(cls) -> str:
        return f"{cls.compared_type_name()}ArrayComparison"


class DateComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[AnyOrderComparison, ModelT, ModelFieldT]):
    """Date comparison class for GraphQL filters.

    This class provides a set of date component comparison operators that
    can be used to filter data based on specific parts of a date.

    Attributes:
        year: Filters based on the year.
        month: Filters based on the month.
        day: Filters based on the day.
        week_day: Filters based on the day of the week.
        week: Filters based on the week number.
        quarter: Filters based on the quarter of the year.
        iso_year: Filters based on the ISO year.
        iso_week_day: Filters based on the ISO day of the week.
    """

    year: AnyOrderComparison | None = None
    month: AnyOrderComparison | None = None
    day: AnyOrderComparison | None = None
    week_day: AnyOrderComparison | None = None
    week: AnyOrderComparison | None = None
    quarter: AnyOrderComparison | None = None
    iso_year: AnyOrderComparison | None = None
    iso_week_day: AnyOrderComparison | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "Date"


class TimeComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[AnyOrderComparison, ModelT, ModelFieldT]):
    """Time comparison class for GraphQL filters.

    This class provides a set of time component comparison operators that
    can be used to filter data based on specific parts of a time.

    Attributes:
        hour: Filters based on the hour.
        minute: Filters based on the minute.
        second: Filters based on the second.
    """

    hour: AnyOrderComparison | None = None
    minute: AnyOrderComparison | None = None
    second: AnyOrderComparison | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "Time"


class TimeDeltaComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[AnyOrderComparison, ModelT, ModelFieldT]):
    days: AnyOrderComparison | None = None
    hours: AnyOrderComparison | None = None
    minutes: AnyOrderComparison | None = None
    seconds: AnyOrderComparison | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "Interval"
