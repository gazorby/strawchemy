from __future__ import annotations

import json
from typing import Any, NewType

from geoalchemy2 import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from geojson_pydantic.geometries import Geometry as PydanticGeometry
from shapely import Geometry, to_geojson

import strawberry
from pydantic import TypeAdapter

__all__ = ("GeoJSON", "StrawberryGeoComparison")

_PydanticGeometryType = TypeAdapter(PydanticGeometry)


def _serialize_geojson(val: Geometry | WKTElement | WKBElement) -> dict[str, Any]:
    if isinstance(val, WKBElement | WKTElement):
        val = to_shape(val)
    return json.loads(to_geojson(val))


def _parse_geojson(val: dict[str, Any]) -> dict[str, Any]:
    _PydanticGeometryType.validate_python(val)
    return val


GeoJSON = strawberry.scalar(
    NewType("GeoJSON", object),
    description=(
        "The `GeoJSON` type represents GEOJson values as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=_parse_geojson,
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)


class StrawberryGeoComparison:
    contains_geometry: GeoJSON | None = strawberry.UNSET
    within_geometry: GeoJSON | None = strawberry.UNSET
    is_null: bool | None = strawberry.UNSET
