from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from typing import Any

import shapely
from geoalchemy2 import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from geojson_pydantic.geometries import Geometry as PydanticGeometry
from geojson_pydantic.geometries import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from pydantic import TypeAdapter
from shapely import Geometry, to_geojson

import strawberry
from strawchemy.strawberry.scalars import new_type

__all__ = (
    "GEO_SCALAR_OVERRIDES",
    "GeoJSON",
    "GeoJSONGeometryCollection",
    "GeoJSONLineString",
    "GeoJSONMultiLineString",
    "GeoJSONMultiPoint",
    "GeoJSONMultiPolygon",
    "GeoJSONPoint",
    "GeoJSONPolygon",
)


@dataclass
class _GeometryHolder:
    geo: PydanticGeometry


_PydanticGeometryType = TypeAdapter(PydanticGeometry)

_PYDANTIC_GEO_ADAPTER_MAP = {
    Point: TypeAdapter(Point),
    Polygon: TypeAdapter(Polygon),
    MultiPolygon: TypeAdapter(MultiPolygon),
    MultiLineString: TypeAdapter(MultiLineString),
    MultiPoint: TypeAdapter(MultiPoint),
    LineString: TypeAdapter(LineString),
    GeometryCollection: TypeAdapter(GeometryCollection),
}


def _serialize_geojson(val: Geometry | WKTElement | WKBElement) -> dict[str, Any]:
    if isinstance(val, (WKBElement, WKTElement)):
        val = to_shape(val)
    return json.loads(to_geojson(val))


def _parse_geojson(val: dict[str, Any], geometry: type[PydanticGeometry] | None = None) -> _GeometryHolder:
    if geometry is None:
        return _GeometryHolder(_PydanticGeometryType.validate_python(val))
    return _GeometryHolder(_PYDANTIC_GEO_ADAPTER_MAP[geometry].validate_python(val))


GeoJSON = strawberry.scalar(
    new_type("GeoJSON", _GeometryHolder),
    description=(
        "The `GeoJSON` type represents GeoJSON values as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=_parse_geojson,
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONPoint = strawberry.scalar(
    new_type("GeoJSONPoint", object),
    description=(
        "The `GeoJSONPoint` type represents GeoJSON Point object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=Point),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiPoint = strawberry.scalar(
    new_type("GeoJSONMultiPoint", object),
    description=(
        "The `GeoJSONMultiPoint` type represents GeoJSON MultiPoint object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiPoint),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONPolygon = strawberry.scalar(
    new_type("GeoJSONPolygon", object),
    description=(
        "The `GeoJSONPolygon` type represents GeoJSON Polygon object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=Polygon),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiPolygon = strawberry.scalar(
    new_type("GeoJSONMultiPolygon", object),
    description=(
        "The `GeoJSONMultiPolygon` type represents GeoJSON MultiPolygon object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiPolygon),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONLineString = strawberry.scalar(
    new_type("GeoJSONLineString", object),
    description=(
        "The `GeoJSONLineString` type represents GeoJSON LineString object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=LineString),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiLineString = strawberry.scalar(
    new_type("GeoJSONMultiLineString", object),
    description=(
        "The `GeoJSONMultiLineString` type represents GeoJSON MultiLineString object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiLineString),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONGeometryCollection = strawberry.scalar(
    new_type("GeoJSONGeometryCollection", object),
    description=(
        "The `GeoJSONGeometryCollection` type represents GeoJSON GeometryCollection object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=GeometryCollection),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)


GEO_SCALAR_OVERRIDES: dict[object, type[Any]] = {
    WKTElement: GeoJSON,
    WKBElement: GeoJSON,
    shapely.Point: GeoJSONPoint,
    shapely.MultiPoint: GeoJSONMultiPoint,
    shapely.Polygon: GeoJSONPolygon,
    shapely.MultiPolygon: GeoJSONMultiPolygon,
    shapely.LineString: GeoJSONLineString,
    shapely.MultiLineString: GeoJSONMultiLineString,
    shapely.GeometryCollection: GeoJSONGeometryCollection,
    shapely.Geometry: GeoJSON,
}
