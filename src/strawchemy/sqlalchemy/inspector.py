from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import inspect
from sqlalchemy.orm import NO_VALUE, DeclarativeBase, QueryableAttribute, registry
from sqlalchemy.types import ARRAY
from strawchemy.config.databases import DatabaseFeatures
from strawchemy.constants import GEO_INSTALLED
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.strawberry.filters import (
    ArrayComparison,
    DateComparison,
    DateTimeComparison,
    EqualityComparison,
    GraphQLComparison,
    JSONComparison,
    OrderComparison,
    SQLITEJSONComparison,
    TextComparison,
    TimeComparison,
    TimeDeltaComparison,
)

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
        (dict,): JSONComparison,
    }
)


def loaded_attributes(model: DeclarativeBase) -> set[str]:
    return {name for name, attr in inspect(model).attrs.items() if attr.loaded_value is not NO_VALUE}


class SQLAlchemyGraphQLInspector(SQLAlchemyInspector):
    def __init__(
        self,
        dialect: SupportedDialect,
        registries: list[registry] | None = None,
        filter_overrides: FilterMap | None = None,
    ) -> None:
        super().__init__(registries)
        self.db_features = DatabaseFeatures.new(dialect)
        self.filters_map = self._filter_map()
        self.filters_map |= filter_overrides or {}

    def _filter_map(self) -> FilterMap:
        filters_map = _DEFAULT_FILTERS_MAP

        if GEO_INSTALLED:
            from geoalchemy2 import WKBElement, WKTElement
            from shapely import Geometry

            from strawchemy.strawberry.filters.geo import GeoComparison

            filters_map |= {(Geometry, WKBElement, WKTElement): GeoComparison}
        if self.db_features.dialect == "sqlite":
            filters_map[(dict,)] = SQLITEJSONComparison
        return filters_map

    @classmethod
    def _is_specialized(cls, type_: type[Any]) -> bool:
        return not hasattr(type_, "__parameters__") or all(
            not isinstance(param, TypeVar) for param in type_.__parameters__
        )

    @classmethod
    def _filter_type(cls, type_: type[Any], sqlalchemy_filter: type[GraphQLComparison]) -> type[GraphQLComparison]:
        return sqlalchemy_filter if cls._is_specialized(sqlalchemy_filter) else sqlalchemy_filter[type_]  # pyright: ignore[reportInvalidTypeArguments]

    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]
    ) -> type[GraphQLComparison]:
        field_type = field_definition.model_field.type
        if isinstance(field_type, ARRAY) and self.db_features.dialect == "postgresql":
            return ArrayComparison[field_type.item_type.python_type]
        return self.get_type_comparison(self.model_field_type(field_definition))

    def get_type_comparison(self, type_: type[Any]) -> type[GraphQLComparison]:
        for types, sqlalchemy_filter in self.filters_map.items():
            if issubclass(type_, types):
                return self._filter_type(type_, sqlalchemy_filter)
        return EqualityComparison[type_]
