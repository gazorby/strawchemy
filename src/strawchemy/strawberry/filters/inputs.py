"""GraphQL filter definitions for DTOs.

This module defines classes and type aliases for creating GraphQL filters
used in data transfer objects (DTOs). It includes comparison classes for
various data types, such as numeric, text, JSONB, arrays, dates, times,
and geometries. These classes allow for building boolean expressions to
compare fields of DTOs in GraphQL queries.
"""

# ruff: noqa: TC003, TC002, TC001
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar

import strawberry
from sqlalchemy import Dialect
from strawberry import UNSET, Private
from strawchemy.strawberry.typing import QueryNodeType

from .base import (
    ArrayFilter,
    DateFilter,
    DateTimeFilter,
    EqualityFilter,
    FilterProtocol,
    JSONFilter,
    OrderFilter,
    TextFilter,
    TimeDeltaFilter,
    TimeFilter,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.orm import QueryableAttribute
    from strawchemy.strawberry.dto import OrderByEnum

__all__ = (
    "ArrayComparison",
    "DateComparison",
    "EqualityComparison",
    "GraphQLComparison",
    "JSONComparison",
    "OrderComparison",
    "TextComparison",
    "TimeComparison",
    "TimeDeltaComparison",
)

T = TypeVar("T")
GraphQLComparisonT = TypeVar("GraphQLComparisonT", bound="GraphQLComparison")
GraphQLFilter: TypeAlias = "GraphQLComparison | OrderByEnum"
AnyGraphQLComparison: TypeAlias = "EqualityComparison[Any] | OrderComparison[Any] | TextComparison | DateComparison | TimeComparison | DateTimeComparison | TimeDeltaComparison | ArrayComparison[Any] | JSONComparison"
AnyOrderGraphQLComparison: TypeAlias = (
    "OrderComparison[Any] | TextComparison | DateComparison | TimeComparison | DateTimeComparison | TimeDeltaComparison"
)

_DESCRIPTION = "Boolean expression to compare {field}. All fields are combined with logical 'AND'"


class GraphQLComparison:
    """Base class for GraphQL comparison filters.

    This class provides a foundation for creating comparison filters
    that can be used in GraphQL queries. It defines the basic structure
    and methods for comparing fields of a specific type.

    Attributes:
        _description: A class variable that stores the description of the
            comparison.
        _field_node: A private attribute that stores the DTO field node.
    """

    __strawchemy_field_node__: Private[QueryNodeType | None] = None
    __strawchemy_filter__: Private[type[FilterProtocol]]

    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        return self.__strawchemy_filter__(self).to_expressions(dialect, model_attribute)

    @property
    def field_node(self) -> QueryNodeType:
        if self.__strawchemy_field_node__ is None:
            raise ValueError
        return self.__strawchemy_field_node__

    @field_node.setter
    def field_node(self, value: QueryNodeType) -> None:
        self.__strawchemy_field_node__ = value


@strawberry.input(
    name="GenericComparison", description=_DESCRIPTION.format(field="fields supporting equality comparisons")
)
class EqualityComparison(GraphQLComparison, Generic[T]):
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

    __strawchemy_filter__ = EqualityFilter

    eq: T | None = UNSET
    neq: T | None = UNSET
    is_null: bool | None = UNSET
    in_: list[T] | None = strawberry.field(name="in", default=UNSET)
    nin: list[T] | None = UNSET


@strawberry.input(name="OrderComparison", description=_DESCRIPTION.format(field="fields supporting order comparisons"))
class OrderComparison(EqualityComparison[T]):
    """Order comparison class for GraphQL filters.

    This class provides a set of numeric comparison operators that can be
    used to filter data based on greater than, less than, and equality.

    Attributes:
        gt: Filters for values greater than this.
        gte: Filters for values greater than or equal to this.
        lt: Filters for values less than this.
        lte: Filters for values less than or equal to this.
    """

    __strawchemy_filter__ = OrderFilter

    gt: T | None = UNSET
    gte: T | None = UNSET
    lt: T | None = UNSET
    lte: T | None = UNSET


@strawberry.input(name="TextComparison", description=_DESCRIPTION.format(field="String fields"))
class TextComparison(OrderComparison[str]):
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

    __strawchemy_filter__ = TextFilter

    like: str | None = UNSET
    nlike: str | None = UNSET
    ilike: str | None = UNSET
    nilike: str | None = UNSET
    regexp: str | None = UNSET
    iregexp: str | None = UNSET
    nregexp: str | None = UNSET
    inregexp: str | None = UNSET
    startswith: str | None = UNSET
    endswith: str | None = UNSET
    contains: str | None = UNSET
    istartswith: str | None = UNSET
    iendswith: str | None = UNSET
    icontains: str | None = UNSET


@strawberry.input(name="JSONComparison", description=_DESCRIPTION.format(field="JSON fields"))
class JSONComparison(EqualityComparison[dict[str, Any]]):
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

    __strawchemy_filter__ = JSONFilter

    contains: dict[str, Any] | None = UNSET
    contained_in: dict[str, Any] | None = UNSET
    has_key: str | None = UNSET
    has_key_all: list[str] | None = UNSET
    has_key_any: list[str] | None = UNSET


@strawberry.input(name="JSONComparison", description=_DESCRIPTION.format(field="JSON fields"))
class SQLITEJSONComparison(EqualityComparison[dict[str, Any]]):
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

    __strawchemy_filter__ = JSONFilter

    has_key: str | None = UNSET
    has_key_all: list[str] | None = UNSET
    has_key_any: list[str] | None = UNSET


@strawberry.input(name="ArrayComparison", description=_DESCRIPTION.format(field="List fields"))
class ArrayComparison(EqualityComparison[T], Generic[T]):
    """Postgres array comparison class for GraphQL filters.

    This class provides a set of array comparison operators that can be
    used to filter data based on containment, overlap, and other
    array-specific properties.

    Attributes:
        contains: Filters for array values that contain all elements in this list.
        contained_in: Filters for array values that are contained in this list.
        overlap: Filters for array values that have any elements in common with this list.
    """

    __strawchemy_filter__ = ArrayFilter

    contains: list[T] | None = UNSET
    contained_in: list[T] | None = UNSET
    overlap: list[T] | None = UNSET


@strawberry.input(name="DateComparison", description=_DESCRIPTION.format(field="Date fields"))
class DateComparison(OrderComparison[date]):
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

    __strawchemy_filter__ = DateFilter

    year: OrderComparison[int] | None = UNSET
    month: OrderComparison[int] | None = UNSET
    day: OrderComparison[int] | None = UNSET
    week_day: OrderComparison[int] | None = UNSET
    week: OrderComparison[int] | None = UNSET
    quarter: OrderComparison[int] | None = UNSET
    iso_year: OrderComparison[int] | None = UNSET
    iso_week_day: OrderComparison[int] | None = UNSET


@strawberry.input(name="TimeComparison", description=_DESCRIPTION.format(field="Time fields"))
class TimeComparison(OrderComparison[time]):
    """Time comparison class for GraphQL filters.

    This class provides a set of time component comparison operators that
    can be used to filter data based on specific parts of a time.

    Attributes:
        hour: Filters based on the hour.
        minute: Filters based on the minute.
        second: Filters based on the second.
    """

    __strawchemy_filter__ = TimeFilter

    hour: OrderComparison[int] | None = UNSET
    minute: OrderComparison[int] | None = UNSET
    second: OrderComparison[int] | None = UNSET


@strawberry.input(name="IntervalComparison", description=_DESCRIPTION.format(field="Interval fields"))
class TimeDeltaComparison(OrderComparison[timedelta]):
    __strawchemy_filter__ = TimeDeltaFilter

    days: OrderComparison[float] | None = UNSET
    hours: OrderComparison[float] | None = UNSET
    minutes: OrderComparison[float] | None = UNSET
    seconds: OrderComparison[float] | None = UNSET


@strawberry.input(name="DateTimeComparison", description=_DESCRIPTION.format(field="DateTime fields"))
class DateTimeComparison(OrderComparison[datetime]):
    __strawchemy_filter__ = DateTimeFilter

    year: OrderComparison[int] | None = UNSET
    month: OrderComparison[int] | None = UNSET
    day: OrderComparison[int] | None = UNSET
    week_day: OrderComparison[int] | None = UNSET
    week: OrderComparison[int] | None = UNSET
    quarter: OrderComparison[int] | None = UNSET
    iso_year: OrderComparison[int] | None = UNSET
    iso_week_day: OrderComparison[int] | None = UNSET

    hour: OrderComparison[int] | None = UNSET
    minute: OrderComparison[int] | None = UNSET
    second: OrderComparison[int] | None = UNSET
