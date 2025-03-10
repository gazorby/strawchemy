"""GraphQL filter definitions for DTOs.

This module defines classes and type aliases for creating GraphQL filters
used in data transfer objects (DTOs). It includes comparison classes for
various data types, such as numeric, text, JSONB, arrays, dates, times,
and geometries. These classes allow for building boolean expressions to
compare fields of DTOs in GraphQL queries.
"""

# ruff: noqa: TC003, TC002, TC001
from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias, TypeVar, override

from geojson_pydantic.geometries import Geometry

from pydantic import BaseModel, Json, PrivateAttr
from strawchemy.dto.base import ModelFieldT, ModelT
from strawchemy.pydantic import RegexPatternStr

if TYPE_CHECKING:
    from .dto import OrderByEnum, QueryNode

__all__ = (
    "DateComparison",
    "GenericComparison",
    "GeoComparison",
    "GraphQLComparison",
    "JSONBComparison",
    "NumericComparison",
    "PostgresArrayComparison",
    "TextComparison",
    "TimeComparison",
)

T = TypeVar("T")
AnyGraphQLComparison = TypeVar("AnyGraphQLComparison", bound="GraphQLComparison[Any, Any]")
AnyNumericComparison = TypeVar("AnyNumericComparison", bound="NumericComparison[Any, Any, Any]")
GraphQLFilter: TypeAlias = "GraphQLComparison[ModelT, ModelFieldT] | OrderByEnum"


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

    _description: ClassVar[str] = (
        "Boolean expression to compare fields of type {field}. All fields are combined with logical 'AND'"
    )
    _field_node: QueryNode[ModelT, Any] | None = PrivateAttr(default=None)

    def to_expressions(self, dialect: Any, model_attribute: Any) -> Any:
        raise NotImplementedError

    @classmethod
    def field_type_name(cls) -> str:
        return cls.__name__

    @classmethod
    def field_name(cls) -> str:
        raise NotImplementedError

    @classmethod
    def field_description(cls) -> str:
        return cls._description.format(field=cls.field_name())

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
        in_: Filters for values present in this list.
        nin_: Filters for values not present in this list.
    """

    eq: T | None = None
    neq: T | None = None
    is_null: bool | None = None
    in_: list[T] | None = None
    nin_: list[T] | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
        type_: type[Any] = cls.__pydantic_generic_metadata__["args"][0]
        return _normalize_field_name(type_)

    @override
    @classmethod
    def field_type_name(cls) -> str:
        return f"{cls.field_name()}Comparison"


class NumericComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[T, ModelT, ModelFieldT]):
    """Numeric comparison class for GraphQL filters.

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
    nregexp: RegexPatternStr | None = None
    startswith: str | None = None
    endswith: str | None = None
    contains: str | None = None
    istartswith: str | None = None
    iendswith: str | None = None
    icontains: str | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
        return _normalize_field_name(str)


class JSONBComparison(GraphQLComparison[ModelT, ModelFieldT]):
    """JSONB comparison class for GraphQL filters.

    This class provides a set of JSONB comparison operators that can be
    used to filter data based on containment, key existence, and other
    JSONB-specific properties.

    Attributes:
        contains: Filters for JSONB values that contain this JSON object.
        ncontains: Filters for JSONB values that do not contain this JSON object.
        contained_in: Filters for JSONB values that are contained in this JSON object.
        ncontained_in: Filters for JSONB values that are not contained in this JSON object.
        has_key: Filters for JSONB values that have this key.
        has_key_all: Filters for JSONB values that have all of these keys.
        has_key_any: Filters for JSONB values that have any of these keys.
        nhas_key: Filters for JSONB values that do not have this key.
        nhas_key_all: Filters for JSONB values that do not have all of these keys.
        nhas_key_any: Filters for JSONB values that do not have any of these keys.
    """

    contains: Json[dict[str, Any]] | None = None
    ncontains: Json[dict[str, Any]] | None = None
    contained_in: Json[dict[str, Any]] | None = None
    ncontained_in: Json[dict[str, Any]] | None = None
    has_key: str | None = None
    has_key_all: list[str] | None = None
    has_key_any: list[str] | None = None
    nhas_key: str | None = None
    nhas_key_all: list[str] | None = None
    nhas_key_any: list[str] | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
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
    def field_type_name(cls) -> str:
        return f"{cls.field_name()}ArrayComparison"


class GeoComparison(GraphQLComparison[ModelT, ModelFieldT]):
    """Geo comparison class for GraphQL filters.

    This class provides a set of geospatial comparison operators that can be
    used to filter data based on geometry containment.

    Attributes:
        contains_geometry: Filters for geometries that contain this geometry.
        within_geometry: Filters for geometries that are within this geometry.
    """

    contains_geometry: Json[Geometry] | None = None
    within_geometry: Json[Geometry] | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
        return "Geometry"


class DateComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[AnyNumericComparison, ModelT, ModelFieldT]):
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

    year: AnyNumericComparison | None = None
    month: AnyNumericComparison | None = None
    day: AnyNumericComparison | None = None
    week_day: AnyNumericComparison | None = None
    week: AnyNumericComparison | None = None
    quarter: AnyNumericComparison | None = None
    iso_year: AnyNumericComparison | None = None
    iso_week_day: AnyNumericComparison | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
        return _normalize_field_name(date)


class TimeComparison(GraphQLComparison[ModelT, ModelFieldT], Generic[AnyNumericComparison, ModelT, ModelFieldT]):
    """Time comparison class for GraphQL filters.

    This class provides a set of time component comparison operators that
    can be used to filter data based on specific parts of a time.

    Attributes:
        hour: Filters based on the hour.
        minute: Filters based on the minute.
        second: Filters based on the second.
    """

    hour: AnyNumericComparison | None = None
    minute: AnyNumericComparison | None = None
    second: AnyNumericComparison | None = None

    @override
    @classmethod
    def field_name(cls) -> str:
        return _normalize_field_name(time)
