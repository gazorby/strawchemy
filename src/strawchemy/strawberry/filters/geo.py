# ruff: noqa: TC003, TC002, TC001
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar, override

from geoalchemy2 import functions as geo_func

import strawberry
from sqlalchemy import ColumnElement, Dialect, null
from sqlalchemy.orm import QueryableAttribute
from strawberry import UNSET
from strawchemy.strawberry.geo import GeoJSON

from .base import FilterProtocol
from .inputs import GraphQLComparison

__all__ = ("GeoComparison",)

T = TypeVar("T")


@dataclass(frozen=True)
class GeoFilter(FilterProtocol):
    comparison: GeoComparison

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.contains_geometry:
            expressions.append(
                geo_func.ST_Contains(
                    model_attribute,
                    geo_func.ST_GeomFromGeoJSON(self.comparison.contains_geometry.geo.model_dump_json()),
                )
            )
        if self.comparison.within_geometry:
            expressions.append(
                geo_func.ST_Within(
                    model_attribute, geo_func.ST_GeomFromGeoJSON(self.comparison.within_geometry.geo.model_dump_json())
                )
            )
        if self.comparison.is_null:
            expressions.append(
                model_attribute.is_(null()) if self.comparison.is_null else model_attribute.is_not(null())
            )

        return expressions


@strawberry.input
class GeoComparison(GraphQLComparison):
    """Geo comparison class for GraphQL filters.

    This class provides a set of geospatial comparison operators that can be
    used to filter data based on geometry containment.

    Attributes:
        contains_geometry: Filters for geometries that contain this geometry.
        within_geometry: Filters for geometries that are within this geometry.
    """

    __strawchemy_filter__ = GeoFilter

    contains_geometry: GeoJSON | None = UNSET
    within_geometry: GeoJSON | None = UNSET
    is_null: bool | None = UNSET
