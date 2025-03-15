from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeVar, override

from shapely import Geometry

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute, registry
from sqlalchemy.types import ARRAY, JSON
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector
from strawchemy.graphql.exceptions import InspectorError
from strawchemy.graphql.inspector import GraphQLInspectorProtocol

from .filters import (
    DateSQLAlchemyFilter,
    DateTimeSQLAlchemyFilter,
    GenericSQLAlchemyFilter,
    NumericSQLAlchemyFilter,
    SQLAlchemyFilterBase,
    TextSQLAlchemyFilter,
    TimeSQLAlchemyFilter,
)
from .filters.geo import GeoSQLAlchemyFilter
from .filters.postgresql import JSONBSQLAlchemyFilter, PostgresArraySQLAlchemyFilter

if TYPE_CHECKING:
    from strawchemy.dto.base import DTOFieldDefinition
    from strawchemy.graphql.dto import GraphQLComparison
    from strawchemy.typing import SupportedDialect

    from .typing import FilterMap


__all__ = ("SQLAlchemyGraphQLInspector",)


T = TypeVar("T", bound=Any)

_DEFAULT_FILTERS_MAP: FilterMap = OrderedDict(
    {
        (datetime,): DateTimeSQLAlchemyFilter,
        (time,): TimeSQLAlchemyFilter,
        (date,): DateSQLAlchemyFilter,
        (bool,): GenericSQLAlchemyFilter,
        (int, float, Decimal): NumericSQLAlchemyFilter,
        (str,): TextSQLAlchemyFilter,
    }
)


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
        self.dialect = dialect
        self.filters_map = _DEFAULT_FILTERS_MAP
        self._dialect_json_types: tuple[type[JSON], ...] | None = None
        if dialect == "postgresql":
            self._dialect_json_types = (postgresql.JSON, postgresql.JSONB)
            self.filters_map |= {(dict,): JSONBSQLAlchemyFilter, (Geometry,): GeoSQLAlchemyFilter}
        self.filters_map |= filter_overrides or {}

    @classmethod
    def _is_specialized(cls, type_: type[Any]) -> bool:
        return all(not isinstance(param, TypeVar) for param in type_.__parameters__)

    @classmethod
    def _filter_type(
        cls, type_: type[Any], sqlalchemy_filter: type[SQLAlchemyFilterBase]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        return sqlalchemy_filter[type_] if not cls._is_specialized(sqlalchemy_filter) else sqlalchemy_filter  # pyright: ignore[reportInvalidTypeArguments]

    @override
    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        field_type = field_definition.model_field.type
        if isinstance(field_type, postgresql.ARRAY):
            return PostgresArraySQLAlchemyFilter[field_type.item_type.python_type]
        if isinstance(field_type, ARRAY):
            msg = "Base SQLAlchemy ARRAY type is not supported. Use backend-specific array type instead."
            raise InspectorError(msg)
        if (
            self._dialect_json_types
            and isinstance(field_type, JSON)
            and not isinstance(field_type, self._dialect_json_types)
        ):
            msg = "Base SQLAlchemy JSON type is not supported. Use backend-specific json type instead."
            raise InspectorError(msg)
        return self.get_type_comparison(self.model_field_type(field_definition))

    @override
    def get_type_comparison(
        self, type_: type[Any]
    ) -> type[GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]]]:
        for types, sqlalchemy_filter in self.filters_map.items():
            if issubclass(type_, types):
                return self._filter_type(type_, sqlalchemy_filter)
        return GenericSQLAlchemyFilter[type_]
