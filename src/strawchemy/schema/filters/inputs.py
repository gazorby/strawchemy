"""GraphQL filter definitions for DTOs.

This module defines classes and type aliases for creating GraphQL filters
used in data transfer objects (DTOs). It includes comparison classes for
various data types, such as numeric, text, JSONB, arrays, dates, times,
and geometries. These classes allow for building boolean expressions to
compare fields of DTOs in GraphQL queries.
"""

# ruff: noqa: TC001
from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias, TypeVar, cast

import strawberry
from strawberry import UNSET, Private
from typing_extensions import Self, assert_never

from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.filters import (
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
from strawchemy.typing import QueryNodeType

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import ColumnElement, Dialect
    from sqlalchemy.orm import QueryableAttribute

    from strawchemy.dto.strawberry import OrderByEnum

__all__ = (
    "ArrayComparison",
    "DateComparison",
    "EqualityComparison",
    "GraphQLComparison",
    "OrderComparison",
    "TextComparison",
    "TimeComparison",
    "TimeDeltaComparison",
    "_JSONComparison",
    "make_full_json_comparison_input",
    "make_sqlite_json_comparison_input",
)

T = TypeVar("T")
_ComparisonT = TypeVar("_ComparisonT", bound="GraphQLComparison")
GraphQLComparisonT = TypeVar("GraphQLComparisonT", bound="GraphQLComparison")

GraphQLFilter: TypeAlias = "GraphQLComparison | OrderByEnum"
AnyGraphQLComparison: TypeAlias = "EqualityComparison[Any] | OrderComparison[Any] | TextComparison | DateComparison | TimeComparison | DateTimeComparison | TimeDeltaComparison | ArrayComparison[Any] | _JSONComparison | _SQLiteJSONComparison"
AnyOrderGraphQLComparison: TypeAlias = (
    "OrderComparison[Any] | TextComparison | DateComparison | TimeComparison | DateTimeComparison | TimeDeltaComparison"
)
FilterLabel: TypeAlias = Literal["equality", "order", "string", "list", "date", "time", "interval", "datetime", "json"]

_DESCRIPTION = "Boolean expression to compare {field}. All fields are combined with logical 'AND'"


def _scalar(t: Any) -> Any:
    return t | None  # eq/neq/gt/lt/...  -> T | None  (the common case; Op's default)


def _seq(t: Any) -> Any:
    return list[t] | None  # in/nin/array ops -> list[T] | None


@dataclass(frozen=True)
class Op:
    """A filter operator: its GraphQL name and how its input value type depends on the data type."""

    graphql_name: str
    """Name as exposed in the schema (e.g. ``in``)."""
    value_type: Callable[[Any], Any] = _scalar
    """``data_type -> annotation`` builder; defaults to scalar ``T | None``."""
    attr: str | None = None
    """Python attribute name when it differs from ``graphql_name`` (e.g. ``in_``)."""

    @property
    def python_attr(self) -> str:
        return self.attr or self.graphql_name


# Equality (order matches EqualityComparison today: eq, neq, is_null, in, nin)
EQUALITY_OPS = (
    Op("eq"),
    Op("neq"),
    Op("is_null", lambda _t: bool | None),
    Op("in", _seq, attr="in_"),
    Op("nin", _seq),
)
# Order increment (gt, gte, lt, lte) — all scalar (default value_type)
ORDER_OPS = (Op("gt"), Op("gte"), Op("lt"), Op("lte"))
# Text increment (exact order of TextComparison today) — always str
TEXT_OPS = tuple(
    Op(n, lambda _t: str | None)
    for n in (
        "like",
        "nlike",
        "ilike",
        "nilike",
        "regexp",
        "iregexp",
        "nregexp",
        "inregexp",
        "startswith",
        "endswith",
        "contains",
        "istartswith",
        "iendswith",
        "icontains",
    )
)
# Array increment (contains, contained_in, overlap) — list-typed
ARRAY_OPS = (Op("contains", _seq), Op("contained_in", _seq), Op("overlap", _seq))
# Date parts (int sub-comparisons); referenced lazily because OrderComparison is defined below
DATE_OPS = tuple(
    Op(n, lambda _t: OrderComparison[int] | None)
    for n in ("year", "month", "day", "week_day", "week", "quarter", "iso_year", "iso_week_day")
)
# Time parts (int sub-comparisons)
TIME_OPS = tuple(Op(n, lambda _t: OrderComparison[int] | None) for n in ("hour", "minute", "second"))
# Interval parts (float sub-comparisons)
INTERVAL_OPS = tuple(Op(n, lambda _t: OrderComparison[float] | None) for n in ("days", "hours", "minutes", "seconds"))


def _filter_description(label: FilterLabel) -> str:
    """Builds a comparison-input description for the given field label.

    Returns:
        The full description string, e.g. ``"Boolean expression to compare String fields. ..."``.
    """
    match label:
        case "equality":
            field = "fields supporting equality comparisons"
        case "order":
            field = "fields supporting order comparisons"
        case "string":
            field = "String fields"
        case "list":
            field = "List fields"
        case "date":
            field = "Date fields"
        case "time":
            field = "Time fields"
        case "interval":
            field = "Interval fields"
        case "datetime":
            field = "DateTime fields"
        case "json":
            field = "JSON fields"
        case _:
            assert_never(label)
    return _DESCRIPTION.format(field=field)


def comparison_input(
    name: str, *, data_type: Any = T, description: str = ""
) -> Callable[[type[_ComparisonT]], type[_ComparisonT]]:
    """Generates a comparison class's own operator fields from its ``__strawchemy_comparison__`` and decorates it.

    ``data_type`` is the TypeVar ``T`` for generic comparisons, or a concrete type (e.g. ``str``).
    """

    def deco(cls: type[_ComparisonT]) -> type[_ComparisonT]:
        annotations, attributes = cls._field_namespace(data_type, cls.__strawchemy_comparison__.operators)
        cls.__annotations__ = {**inspect.get_annotations(cls), **annotations}
        for attr, value in attributes.items():
            setattr(cls, attr, value)
        return strawberry.input(name=name, description=description)(cls)

    return deco


@dataclass(frozen=True, slots=True)
class _StrawchemyComparison:
    """Static metadata for a comparison class."""

    filter: type[FilterProtocol]
    """The query-time filter that turns this comparison into SQL expressions."""
    operators: tuple[Op, ...] = ()
    """The comparison's own operators (merged across the MRO by ``_all_operators``)."""


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
    __strawchemy_comparison__: ClassVar[_StrawchemyComparison]
    _restricted_cache: ClassVar[dict[tuple[type[Any], Any, tuple[str, ...]], type[GraphQLComparison]]] = {}

    @classmethod
    def _all_operators(cls) -> tuple[Op, ...]:
        """Full operator set for this comparison, collected base-first across the MRO (deduped)."""
        seen: set[str] = set()
        collected: list[Op] = []
        for klass in reversed(inspect.getmro(cls)):
            definition: _StrawchemyComparison | None = klass.__dict__.get("__strawchemy_comparison__")
            for op in definition.operators if definition is not None else ():
                if op.graphql_name not in seen:
                    seen.add(op.graphql_name)
                    collected.append(op)
        return tuple(collected)

    @classmethod
    def restricted(cls, data_type: Any, ops: tuple[str, ...]) -> type[Self]:
        """Builds (and caches) a comparison input over ``data_type`` exposing only ``ops``.

        The result is a standalone strawberry input carrying every operator attribute (unselected
        ones defaulted ``UNSET``) so the query-time ``*Filter.to_expressions`` keep working, and the
        same ``__strawchemy_comparison__.filter`` as ``cls``.

        Args:
            data_type: The scalar type the operators compare against.
            ops: Selected GraphQL operator names (order-independent).

        Returns:
            A strawberry input type restricted to the selected operators.

        Raises:
            StrawchemyFieldError: If an operator is not defined for this comparison.
        """
        chosen_ops = tuple(sorted(set(ops)))
        cache_key = (cls, data_type, chosen_ops)
        if (cached := GraphQLComparison._restricted_cache.get(cache_key)) is not None:
            return cast("type[Self]", cached)

        all_ops = cls._all_operators()
        ops_by_name = {op.graphql_name: op for op in all_ops}

        if invalid_ops := [op for op in chosen_ops if op not in ops_by_name]:
            msg = f"Operator(s) {invalid_ops} not valid for {cls.__name__}; allowed: {sorted(ops_by_name)}"
            raise StrawchemyFieldError(msg)

        annotations, attributes = cls._field_namespace(data_type, tuple(ops_by_name[op] for op in chosen_ops))
        namespace: dict[str, Any] = {
            "__annotations__": annotations,
            "__strawchemy_comparison__": _StrawchemyComparison(filter=cls.__strawchemy_comparison__.filter),
            **attributes,
        }
        for op in all_ops:  # unselected ops present as UNSET so query-time filters work
            namespace.setdefault(op.python_attr, UNSET)

        # Build restricted type
        suffix = "".join(part.capitalize() for op in chosen_ops for part in op.split("_"))
        type_name = f"{cls.__name__}{data_type.__name__.capitalize()}{suffix}"
        built = cast(
            "type[Self]",
            strawberry.input(name=type_name, description=f"{cls.__name__} restricted to {', '.join(chosen_ops)}")(
                type(type_name, (GraphQLComparison,), namespace)
            ),
        )
        GraphQLComparison._restricted_cache[cache_key] = built
        return built

    @classmethod
    def _field_namespace(cls, data_type: Any, ops: tuple[Op, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Builds (annotations, attributes) for ``ops`` resolved against ``data_type``."""
        annotations = {op.python_attr: op.value_type(data_type) for op in ops}
        attributes = {
            op.python_attr: (strawberry.field(name=op.graphql_name, default=UNSET) if op.attr else UNSET) for op in ops
        }
        return annotations, attributes

    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        return self.__strawchemy_comparison__.filter(self).to_expressions(dialect, model_attribute)

    @property
    def field_node(self) -> QueryNodeType:
        if self.__strawchemy_field_node__ is None:
            raise ValueError
        return self.__strawchemy_field_node__

    @field_node.setter
    def field_node(self, value: QueryNodeType) -> None:
        self.__strawchemy_field_node__ = value


@comparison_input("GenericComparison", description=_filter_description("equality"))
class EqualityComparison(GraphQLComparison, Generic[T]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=EqualityFilter, operators=EQUALITY_OPS)

    if TYPE_CHECKING:
        # Generated at runtime from ``__strawchemy_comparison__.operators``; declared for type checkers.
        eq: T | None
        neq: T | None
        is_null: bool | None
        in_: list[T] | None
        nin: list[T] | None


@comparison_input("OrderComparison", description=_filter_description("order"))
class OrderComparison(EqualityComparison[T]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=OrderFilter, operators=ORDER_OPS)

    if TYPE_CHECKING:
        gt: T | None
        gte: T | None
        lt: T | None
        lte: T | None


@comparison_input("TextComparison", data_type=str, description=_filter_description("string"))
class TextComparison(OrderComparison[str]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=TextFilter, operators=TEXT_OPS)

    if TYPE_CHECKING:
        like: str | None
        nlike: str | None
        ilike: str | None
        nilike: str | None
        regexp: str | None
        iregexp: str | None
        nregexp: str | None
        inregexp: str | None
        startswith: str | None
        endswith: str | None
        contains: str | None
        istartswith: str | None
        iendswith: str | None
        icontains: str | None


@comparison_input("ArrayComparison", description=_filter_description("list"))
class ArrayComparison(EqualityComparison[T], Generic[T]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=ArrayFilter, operators=ARRAY_OPS)

    if TYPE_CHECKING:
        contains: list[T] | None
        contained_in: list[T] | None
        overlap: list[T] | None


@comparison_input("DateComparison", data_type=date, description=_filter_description("date"))
class DateComparison(OrderComparison[date]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=DateFilter, operators=DATE_OPS)

    if TYPE_CHECKING:
        year: OrderComparison[int] | None
        month: OrderComparison[int] | None
        day: OrderComparison[int] | None
        week_day: OrderComparison[int] | None
        week: OrderComparison[int] | None
        quarter: OrderComparison[int] | None
        iso_year: OrderComparison[int] | None
        iso_week_day: OrderComparison[int] | None


@comparison_input("TimeComparison", data_type=time, description=_filter_description("time"))
class TimeComparison(OrderComparison[time]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=TimeFilter, operators=TIME_OPS)

    if TYPE_CHECKING:
        hour: OrderComparison[int] | None
        minute: OrderComparison[int] | None
        second: OrderComparison[int] | None


@comparison_input("IntervalComparison", data_type=timedelta, description=_filter_description("interval"))
class TimeDeltaComparison(OrderComparison[timedelta]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=TimeDeltaFilter, operators=INTERVAL_OPS)

    if TYPE_CHECKING:
        days: OrderComparison[float] | None
        hours: OrderComparison[float] | None
        minutes: OrderComparison[float] | None
        seconds: OrderComparison[float] | None


@comparison_input("DateTimeComparison", data_type=datetime, description=_filter_description("datetime"))
class DateTimeComparison(OrderComparison[datetime]):
    __strawchemy_comparison__ = _StrawchemyComparison(filter=DateTimeFilter, operators=(*DATE_OPS, *TIME_OPS))

    if TYPE_CHECKING:
        year: OrderComparison[int] | None
        month: OrderComparison[int] | None
        day: OrderComparison[int] | None
        week_day: OrderComparison[int] | None
        week: OrderComparison[int] | None
        quarter: OrderComparison[int] | None
        iso_year: OrderComparison[int] | None
        iso_week_day: OrderComparison[int] | None
        hour: OrderComparison[int] | None
        minute: OrderComparison[int] | None
        second: OrderComparison[int] | None


class _JSONComparison(EqualityComparison[dict[str, Any]]):
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

    __strawchemy_comparison__ = _StrawchemyComparison(filter=JSONFilter)

    contains: dict[str, Any] | None = UNSET
    contained_in: dict[str, Any] | None = UNSET
    has_key: str | None = UNSET
    has_key_all: list[str] | None = UNSET
    has_key_any: list[str] | None = UNSET


class _SQLiteJSONComparison(EqualityComparison[dict[str, Any]]):
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

    __strawchemy_comparison__ = _StrawchemyComparison(filter=JSONFilter)

    has_key: str | None = UNSET
    has_key_all: list[str] | None = UNSET
    has_key_any: list[str] | None = UNSET


@cache
def make_full_json_comparison_input() -> type[_JSONComparison]:
    return cast(
        "type[_JSONComparison]",
        strawberry.input(name="JSONComparison", description=_filter_description("json"))(_JSONComparison),
    )


@cache
def make_sqlite_json_comparison_input() -> type[_SQLiteJSONComparison]:
    return cast(
        "type[_SQLiteJSONComparison]",
        strawberry.input(name="JSONComparison", description=_filter_description("json"))(_SQLiteJSONComparison),
    )
