from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeVar, override

from sqlalchemy import inspect
from sqlalchemy.orm import NO_VALUE, DeclarativeBase, QueryableAttribute, registry
from sqlalchemy.types import ARRAY
from strawchemy.config.databases import DatabaseFeatures
from strawchemy.constants import GEO_INSTALLED
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.graphql.inspector import GraphQLInspectorProtocol

from .filters import (
    DateSQLAlchemyFilter,
    DateTimeSQLAlchemyFilter,
    GenericSQLAlchemyFilter,
    JSONSQLAlchemyFilter,
    OrderSQLAlchemyFilter,
    SQLAlchemyFilterBase,
    TextSQLAlchemyFilter,
    TimeDeltaSQLAlchemyFilter,
    TimeSQLAlchemyFilter,
)
from .filters.postgresql import PostgresArraySQLAlchemyFilter

if TYPE_CHECKING:
    from strawchemy.dto.base import DTOFieldDefinition
    from strawchemy.graphql.dto import GraphQLComparison
    from strawchemy.typing import SupportedDialect

    from .typing import FilterMap


__all__ = ("SQLAlchemyGraphQLInspector", "loaded_attributes")


T = TypeVar("T", bound=Any)


_DEFAULT_FILTERS_MAP: FilterMap = OrderedDict(
    {
        (timedelta,): TimeDeltaSQLAlchemyFilter,
        (datetime,): DateTimeSQLAlchemyFilter,
        (time,): TimeSQLAlchemyFilter,
        (date,): DateSQLAlchemyFilter,
        (bool,): GenericSQLAlchemyFilter,
        (int, float, Decimal): OrderSQLAlchemyFilter,
        (str,): TextSQLAlchemyFilter,
    }
)


def loaded_attributes(model: DeclarativeBase) -> set[str]:
    return {name for name, attr in inspect(model).attrs.items() if attr.loaded_value is not NO_VALUE}


class SQLAlchemyGraphQLInspector(
    SQLAlchemyInspector, GraphQLInspectorProtocol[DeclarativeBase, QueryableAttribute[Any]]
):
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

        if self.db_features.supports_json:
            filters_map |= {(dict,): JSONSQLAlchemyFilter}
            if GEO_INSTALLED:
                from geoalchemy2 import WKBElement, WKTElement
                from shapely import Geometry

                from .filters.geo import GeoSQLAlchemyFilter

                filters_map |= {(Geometry, WKBElement, WKTElement): GeoSQLAlchemyFilter}
        return filters_map

    @classmethod
    def _is_specialized(cls, type_: type[Any]) -> bool:
        return all(not isinstance(param, TypeVar) for param in type_.__parameters__)

    @classmethod
    def _filter_type(
        cls, type_: type[Any], sqlalchemy_filter: type[SQLAlchemyFilterBase]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        return sqlalchemy_filter if cls._is_specialized(sqlalchemy_filter) else sqlalchemy_filter[type_]  # pyright: ignore[reportInvalidTypeArguments]

    @override
    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        field_type = field_definition.model_field.type
        if isinstance(field_type, ARRAY) and self.db_features.dialect == "postgresql":
            return PostgresArraySQLAlchemyFilter[field_type.item_type.python_type]
        return self.get_type_comparison(self.model_field_type(field_definition))

    @override
    def get_type_comparison(
        self, type_: type[Any]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        for types, sqlalchemy_filter in self.filters_map.items():
            if issubclass(type_, types):
                return self._filter_type(type_, sqlalchemy_filter)
        return GenericSQLAlchemyFilter[type_]
