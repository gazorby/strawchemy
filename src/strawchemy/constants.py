from __future__ import annotations

from importlib.util import find_spec

__all__ = ("GEO_INSTALLED",)

GEO_INSTALLED: bool = all(find_spec(package) is not None for package in ("geoalchemy2", "shapely"))

LIMIT_KEY = "limit"
OFFSET_KEY = "offset"
ORDER_BY_KEY = "order_by"
FILTER_KEY = "filter"
DISTINCT_ON_KEY = "distinct_on"

AGGREGATIONS_KEY = "aggregations"
NODES_KEY = "nodes"

DATA_KEY = "data"
JSON_PATH_KEY = "path"
