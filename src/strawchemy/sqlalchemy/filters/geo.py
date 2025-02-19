from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from geoalchemy2 import functions as geo_func

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.graphql.filters import GeoComparison

from .base import SQLAlchemyFilterBase

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Dialect

__all__ = ("GeoSQLAlchemyFilter",)


class GeoSQLAlchemyFilter(SQLAlchemyFilterBase, GeoComparison[DeclarativeBase, QueryableAttribute[Any]]):
    """Geo SQLAlchemy filter for geometry comparison operations.

    This class extends GeoComparison and adds filtering
    capabilities for contains_geometry and within_geometry operations.
    """

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = []

        if "contains_geometry" in self.model_fields_set and self.contains_geometry:
            expressions.append(
                geo_func.ST_Contains(
                    model_attribute, geo_func.ST_GeomFromGeoJSON(self.contains_geometry.model_dump_json())
                )
            )
        if "within_geometry" in self.model_fields_set and self.within_geometry:
            expressions.append(
                geo_func.ST_Contains(
                    model_attribute, geo_func.ST_GeomFromGeoJSON(self.within_geometry.model_dump_json())
                )
            )

        return expressions
