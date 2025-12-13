"""Provides an inspector for SQLAlchemy models to determine GraphQL filter types.

This module defines `SQLAlchemyGraphQLInspector`, which extends the base
`SQLAlchemyInspector` from `strawchemy.dto.inspectors.sqlalchemy`. It maps
SQLAlchemy column types and model attributes to appropriate GraphQL comparison
filter types (e.g., `TextComparison`, `OrderComparison`). This process considers
database-specific features (via `DatabaseFeatures`) and allows for custom
filter overrides. The module also includes utility functions like `loaded_attributes`.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy.orm import NO_VALUE, DeclarativeBase, QueryableAttribute, registry
from sqlalchemy.types import ARRAY

from sqlalchemy import inspect
from strawchemy.config.databases import DatabaseFeatures
from strawchemy.constants import GEO_INSTALLED
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.strawberry.filters import (
    ArrayComparison,
    DateComparison,
    DateTimeComparison,
    EqualityComparison,
    GraphQLComparison,
    OrderComparison,
    TextComparison,
    TimeComparison,
    TimeDeltaComparison,
)
from strawchemy.strawberry.filters.inputs import make_full_json_comparison_input, make_sqlite_json_comparison_input

if TYPE_CHECKING:
    from strawchemy.dto.base import DTOFieldDefinition
    from strawchemy.typing import SupportedDialect

    from .typing import FilterMap


__all__ = ("SQLAlchemyGraphQLInspector", "loaded_attributes")


T = TypeVar("T", bound=Any)


_DEFAULT_FILTERS_MAP: FilterMap = OrderedDict(
    {
        (timedelta,): TimeDeltaComparison,
        (datetime,): DateTimeComparison,
        (time,): TimeComparison,
        (date,): DateComparison,
        (bool,): EqualityComparison,
        (int, float, Decimal): OrderComparison,
        (str,): TextComparison,
    }
)


def loaded_attributes(model: DeclarativeBase) -> set[str]:
    """Identifies attributes of a SQLAlchemy model instance that have been loaded.

    This function inspects the given SQLAlchemy model instance and returns a set
    of attribute names for which the value has been loaded from the database
    (i.e., the value is not `sqlalchemy.orm.NO_VALUE`).

    Args:
        model: The SQLAlchemy `DeclarativeBase` instance to inspect.

    Returns:
        A set of strings, where each string is the name of a loaded attribute.
    """
    return {name for name, attr in inspect(model).attrs.items() if attr.loaded_value is not NO_VALUE}


class SQLAlchemyGraphQLInspector(SQLAlchemyInspector):
    """Inspects SQLAlchemy models to determine appropriate GraphQL filter types.

    This inspector extends `SQLAlchemyInspector` to provide mappings from
    SQLAlchemy model attributes and Python types to specific GraphQL comparison
    filter input types (e.g., `TextComparison`, `OrderComparison`).

    It takes into account the database dialect's features (via `DatabaseFeatures`)
    to select suitable filters, for example, for JSON or geospatial types.
    Custom filter mappings can also be provided through `filter_overrides`.

    Key methods `get_field_comparison` and `get_type_comparison` are used to
    retrieve the corresponding filter types.
    """

    def __init__(
        self,
        dialect: SupportedDialect,
        registries: list[registry] | None = None,
        filter_overrides: FilterMap | None = None,
    ) -> None:
        """Initializes the SQLAlchemyGraphQLInspector.

        Args:
            dialect: The SQL dialect of the target database (e.g., "postgresql", "sqlite").
            registries: An optional list of SQLAlchemy registries to inspect.
                If None, the default registry is used.
            filter_overrides: An optional mapping to override or extend the default
                Python type to GraphQL filter type mappings.
        """
        super().__init__(registries)
        self.db_features = DatabaseFeatures.new(dialect)
        self.filters_map = self._filter_map()
        self.filters_map |= filter_overrides or {}

    def _filter_map(self) -> FilterMap:
        """Constructs the map of Python types to GraphQL filter comparison types.

        Starts with a default set of filters (`_DEFAULT_FILTERS_MAP`).
        If GeoAlchemy is installed (`GEO_INSTALLED`), it adds mappings for
        geospatial types to `GeoComparison`.
        It then adds mappings for `dict` to appropriate JSON comparison
        types based on whether the dialect is SQLite or another database
        that supports more advanced JSON operations.

        Returns:
            The constructed `FilterMap`.
        """
        filters_map = _DEFAULT_FILTERS_MAP

        if GEO_INSTALLED:
            from geoalchemy2 import WKBElement, WKTElement  # noqa: PLC0415
            from shapely import Geometry  # noqa: PLC0415

            from strawchemy.strawberry.filters.geo import GeoComparison  # noqa: PLC0415

            filters_map |= {(Geometry, WKBElement, WKTElement): GeoComparison}
        if self.db_features.dialect == "sqlite":
            filters_map[(dict, dict)] = make_sqlite_json_comparison_input()
        else:
            filters_map[(dict, dict)] = make_full_json_comparison_input()
        return filters_map

    @classmethod
    def _is_specialized(cls, type_: type[Any]) -> bool:
        """Checks if a generic type is fully specialized.

        A type is considered specialized if it has no type parameters (`__parameters__`)
        or if all its type parameters are concrete types (not `TypeVar`).

        Args:
            type_: The type to check.

        Returns:
            True if the type is specialized, False otherwise.
        """
        return not hasattr(type_, "__parameters__") or all(
            not isinstance(param, TypeVar) for param in type_.__parameters__
        )

    @classmethod
    def _filter_type(cls, type_: type[Any], sqlalchemy_filter: type[GraphQLComparison]) -> type[GraphQLComparison]:
        """Potentially specializes a generic GraphQL filter type with a Python type.

        If the provided `sqlalchemy_filter` is a generic type (e.g., `OrderComparison[T]`)
        and is not yet specialized, this method specializes it using `type_`
        (e.g., `OrderComparison[int]`). If `sqlalchemy_filter` is already specialized
        or not generic, it's returned as is.

        Args:
            type_: The Python type to use for specialization if needed.
            sqlalchemy_filter: The GraphQL filter type, which might be generic.

        Returns:
            The (potentially specialized) GraphQL filter type.
        """
        return sqlalchemy_filter if cls._is_specialized(sqlalchemy_filter) else sqlalchemy_filter[type_]  # pyright: ignore[reportInvalidTypeArguments]

    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]
    ) -> type[GraphQLComparison]:
        """Determines the GraphQL comparison filter type for a DTO field.

        This method inspects the type of the given DTO field.
        For `ARRAY` types on PostgreSQL, it returns a specialized `ArrayComparison`.
        Otherwise, it delegates to `get_type_comparison` using the Python type
        of the model field.

        Args:
            field_definition: The DTO field definition, which contains information
                about the model attribute and its type.

        Returns:
            The GraphQL comparison filter type suitable for the field.
        """
        field_type = field_definition.model_field.type
        if isinstance(field_type, ARRAY) and self.db_features.dialect == "postgresql":
            return ArrayComparison[field_type.item_type.python_type]
        return self.get_type_comparison(self.model_field_type(field_definition))

    def get_type_comparison(self, type_: type[Any]) -> type[GraphQLComparison]:
        """Determines the GraphQL comparison filter type for a Python type.

        It iterates through the `self.filters_map` (which includes default
        and dialect-specific filters) to find a filter type that matches
        the provided Python `type_`.
        If a direct match or a superclass match is found, the corresponding
        filter type is returned, potentially specialized using `_filter_type`.
        If no specific filter is found in the map, it defaults to
        `EqualityComparison` specialized with the given `type_`.

        Args:
            type_: The Python type for which to find a GraphQL filter.

        Returns:
            The GraphQL comparison filter type suitable for the Python type.
        """
        for types, sqlalchemy_filter in self.filters_map.items():
            if issubclass(type_, types):
                return self._filter_type(type_, sqlalchemy_filter)
        return EqualityComparison[type_]
