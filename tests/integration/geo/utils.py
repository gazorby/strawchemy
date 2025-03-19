from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import quote

from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely import to_geojson

from tests.integration.fixtures import GEO_DATA

if TYPE_CHECKING:
    from geoalchemy2 import WKBElement


__all__ = ("_element_to_geojson_io_url", "geo_data_visualization_urls")


def _element_to_geojson_io_url(element: WKBElement | WKTElement | str) -> str:
    base_url = "https://geojson.io/#data=data:application/json,"
    if isinstance(element, str):
        element = WKTElement(element)
    geojson = to_geojson(to_shape(element))
    return f"{base_url}{quote(geojson)}"


def geo_data_visualization_urls() -> None:
    data = [
        {key: _element_to_geojson_io_url(value) for key, value in row.items() if key != "id" and value is not None}
        for row in GEO_DATA
    ]
    print(json.dumps(data, indent=2))  # noqa: T201
