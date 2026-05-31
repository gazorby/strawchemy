from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from typing import Any, NewType

import shapely
import strawberry
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

_PYDANTIC_GEO_ADAPTER_MAP: dict[type[PydanticGeometry], TypeAdapter[Any]] = {
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


GeoJSON = NewType("GeoJSON", _GeometryHolder)

_GeoJSONScalar = strawberry.scalar(
    name="GeoJSON",
    description=(
        "The `GeoJSON` type represents GeoJSON values as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=_parse_geojson,
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONPoint = strawberry.scalar(
    name="GeoJSONPoint",
    description=(
        "The `GeoJSONPoint` type represents GeoJSON Point object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=Point),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiPoint = strawberry.scalar(
    name="GeoJSONMultiPoint",
    description=(
        "The `GeoJSONMultiPoint` type represents GeoJSON MultiPoint object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiPoint),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONPolygon = strawberry.scalar(
    name="GeoJSONPolygon",
    description=(
        "The `GeoJSONPolygon` type represents GeoJSON Polygon object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=Polygon),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiPolygon = strawberry.scalar(
    name="GeoJSONMultiPolygon",
    description=(
        "The `GeoJSONMultiPolygon` type represents GeoJSON MultiPolygon object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiPolygon),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONLineString = strawberry.scalar(
    name="GeoJSONLineString",
    description=(
        "The `GeoJSONLineString` type represents GeoJSON LineString object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=LineString),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONMultiLineString = strawberry.scalar(
    name="GeoJSONMultiLineString",
    description=(
        "The `GeoJSONMultiLineString` type represents GeoJSON MultiLineString object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=MultiLineString),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)

GeoJSONGeometryCollection = strawberry.scalar(
    name="GeoJSONGeometryCollection",
    description=(
        "The `GeoJSONGeometryCollection` type represents GeoJSON GeometryCollection object as specified by "
        "[RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)"
    ),
    serialize=_serialize_geojson,
    parse_value=partial(_parse_geojson, geometry=GeometryCollection),
    specified_by_url="https://datatracker.ietf.org/doc/html/rfc7946",
)


GEO_SCALAR_OVERRIDES: dict[object, Any] = {
    GeoJSON: _GeoJSONScalar,
    WKTElement: _GeoJSONScalar,
    WKBElement: _GeoJSONScalar,
    shapely.Point: GeoJSONPoint,
    shapely.MultiPoint: GeoJSONMultiPoint,
    shapely.Polygon: GeoJSONPolygon,
    shapely.MultiPolygon: GeoJSONMultiPolygon,
    shapely.LineString: GeoJSONLineString,
    shapely.MultiLineString: GeoJSONMultiLineString,
    shapely.GeometryCollection: GeoJSONGeometryCollection,
    shapely.Geometry: _GeoJSONScalar,
}
