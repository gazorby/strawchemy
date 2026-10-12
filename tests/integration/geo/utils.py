from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import quote

from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely import to_geojson

if TYPE_CHECKING:
    from geoalchemy2 import WKBElement


__all__ = ("GEO_DATA", "_element_to_geojson_io_url", "geo_data_visualization_urls")

GEO_DATA = [
    # Complete record with all geometry types
    {
        "id": 1,
        "point_required": "POINT(0 0)",  # Origin point
        "point": "POINT(1 1)",  # Simple point
        "line_string": "LINESTRING(0 0, 1 1, 2 2)",  # Simple line with 3 points
        "polygon": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",  # Simple square
        "multi_point": "MULTIPOINT((0 0), (1 1), (2 2))",  # 3 points
        "multi_line_string": "MULTILINESTRING((0 0, 1 1), (2 2, 3 3))",  # 2 lines
        "multi_polygon": "MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)), ((2 2, 2 3, 3 3, 3 2, 2 2)))",  # 2 squares
        "geometry": "POINT(5 5)",  # Using point as generic geometry
    },
    # Record with only required fields
    {
        "id": 2,
        "point_required": "POINT(10 20)",  # Required point
        "point": None,
        "line_string": None,
        "polygon": None,
        "multi_point": None,
        "multi_line_string": None,
        "multi_polygon": None,
        "geometry": None,
    },
    # Record with complex geometries
    {
        "id": 3,
        "point_required": "POINT(-122.6 45.5)",  # Real-world coordinates (Portland, OR)
        "point": "POINT(-74.0060 40.7128)",  # New York City
        "line_string": "LINESTRING(-122.4194 37.7749, -118.2437 34.0522, -74.0060 40.7128)",  # SF to LA to NYC
        "polygon": "POLYGON((-122.4194 37.7749, -122.4194 37.8, -122.4 37.8, -122.4 37.7749, -122.4194 37.7749))",
        # Area in SF
        "multi_point": "MULTIPOINT((-122.4194 37.7749), (-118.2437 34.0522), (-74.0060 40.7128))",  # Major US cities
        "multi_line_string": "MULTILINESTRING((-122.4194 37.7749, -118.2437 34.0522), (-118.2437 34.0522, -74.0060 40.7128))",
        # Route segments
        "multi_polygon": "MULTIPOLYGON(((-122.42 37.78, -122.42 37.8, -122.4 37.8, -122.4 37.78, -122.42 37.78)), ((-118.25 34.05, -118.25 34.06, -118.24 34.06, -118.24 34.05, -118.25 34.05)))",
        # Areas in SF and LA
        "geometry": "LINESTRING(-122.4194 37.7749, -74.0060 40.7128)",  # Direct SF to NYC
    },
]


def _element_to_geojson_io_url(element: WKBElement | WKTElement | str) -> str:
    base_url = "https://geojson.io/#data=data:application/json,"
    if isinstance(element, str):
        element = WKTElement(element)
    geojson = to_geojson(to_shape(element))
    return f"{base_url}{quote(geojson)}"


def geo_data_visualization_urls() -> None:
    data = [
        {key: _element_to_geojson_io_url(str(value)) for key, value in row.items() if key != "id" and value is not None}
        for row in GEO_DATA
    ]
    print(json.dumps(data, indent=2))  # noqa: T201


def _swap_point(point: str) -> str:
    coords = point.split()
    return f"{coords[1]} {coords[0]}" if len(coords) == 2 else point


def _swap_wkt_point(value: str) -> str:
    # For POINT, just swap the coordinates
    coords = value.strip("()").split()
    if len(coords) == 2:
        return f"POINT({coords[1]} {coords[0]})"
    msg = f"Not a valid wkt POINT {value}"
    raise ValueError(msg)


def _swap_wkt_linestring(value: str) -> str:
    # For LINESTRING, swap each point
    points = value.strip("()").split(", ")
    inverted_points = [_swap_point(p) for p in points]
    return f"LINESTRING({', '.join(inverted_points)})"


def _swap_wkt_polygon(value: str) -> str:
    # For POLYGON, swap each point in each ring
    rings = value.strip("()").split("), (")
    inverted_rings = []
    for ring in rings:
        stripped_ring = ring.strip("()")
        points = stripped_ring.split(", ")
        inverted_points = [_swap_point(p) for p in points]
        inverted_rings.append(f"({', '.join(inverted_points)})")
    return f"POLYGON({', '.join(inverted_rings)})"


def _swap_wkt_multipoint(value: str) -> str:
    # For MULTIPOINT, swap each point
    points = value.strip("()").split("), (")
    inverted_points = []
    for point in points:
        stripped_point = point.strip("()")
        inverted_points.append(f"({_swap_point(stripped_point)})")
    return f"MULTIPOINT({', '.join(inverted_points)})"


def _swap_wkt_multilinestring(value: str) -> str:
    # For MULTILINESTRING, swap each point in each linestring
    linestrings = value.strip("()").split("), (")
    inverted_linestrings = []
    for linestring in linestrings:
        stripped_linestring = linestring.strip("()")
        points = stripped_linestring.split(", ")
        inverted_points = [_swap_point(p) for p in points]
        inverted_linestrings.append(f"({', '.join(inverted_points)})")
    return f"MULTILINESTRING({', '.join(inverted_linestrings)})"


def _swap_wkt_multipolygon(value: str) -> str:
    # For MULTIPOLYGON, swap each point in each ring in each polygon
    polygons = value.strip("()").split(")), ((")
    inverted_polygons = []
    for polygon in polygons:
        stripped_polygon = polygon.strip("()")
        rings = stripped_polygon.split("), (")
        inverted_rings = []
        for ring in rings:
            stripped_ring = ring.strip("()")
            points = stripped_ring.split(", ")
            inverted_points = [_swap_point(p) for p in points]
            inverted_rings.append(f"({', '.join(inverted_points)})")
        inverted_polygons.append(f"({', '.join(inverted_rings)})")
    return f"MULTIPOLYGON({', '.join(inverted_polygons)})"


def invert_wkt_coordinates(wkt_str: str) -> str:
    """Invert lon,lat to lat,lon in WKT geometry strings."""
    # Extract the geometry type and coordinates part
    parts = wkt_str.split("(", 1)
    geom_type = parts[0].strip()
    coords_part = f"({parts[1]}"
    swapped_wkt = wkt_str

    # Handle different geometry types
    if geom_type == "POINT":
        swapped_wkt = _swap_wkt_point(coords_part)
    elif geom_type == "LINESTRING":
        swapped_wkt = _swap_wkt_linestring(coords_part)
    elif geom_type == "POLYGON":
        swapped_wkt = _swap_wkt_polygon(coords_part)
    elif geom_type == "MULTIPOINT":
        swapped_wkt = _swap_wkt_multipoint(coords_part)
    elif geom_type == "MULTILINESTRING":
        swapped_wkt = _swap_wkt_multilinestring(coords_part)
    elif geom_type == "MULTIPOLYGON":
        swapped_wkt = _swap_wkt_multipolygon(coords_part)

    return swapped_wkt
