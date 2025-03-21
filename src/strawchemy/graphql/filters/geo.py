# ruff: noqa: TC003, TC002, TC001
from __future__ import annotations

from typing import TypeVar, override

from geojson_pydantic.geometries import Geometry

from strawchemy.dto.base import ModelFieldT, ModelT

from .base import GraphQLComparison

__all__ = ("GeoComparison",)

T = TypeVar("T")


class GeoComparison(GraphQLComparison[ModelT, ModelFieldT]):
    """Geo comparison class for GraphQL filters.

    This class provides a set of geospatial comparison operators that can be
    used to filter data based on geometry containment.

    Attributes:
        contains_geometry: Filters for geometries that contain this geometry.
        within_geometry: Filters for geometries that are within this geometry.
    """

    contains_geometry: Geometry | None = None
    within_geometry: Geometry | None = None
    is_null: bool | None = None

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        return "Geometry"
