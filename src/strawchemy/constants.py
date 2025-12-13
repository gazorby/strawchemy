from __future__ import annotations

from importlib.util import find_spec

__all__ = (
    "AGGREGATIONS_KEY",
    "DATA_KEY",
    "DISTINCT_ON_KEY",
    "FILTER_KEY",
    "GEO_INSTALLED",
    "JSON_PATH_KEY",
    "LIMIT_KEY",
    "NODES_KEY",
    "OFFSET_KEY",
    "ORDER_BY_KEY",
    "UPSERT_CONFLICT_FIELDS",
    "UPSERT_UPDATE_FIELDS",
)

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

UPSERT_UPDATE_FIELDS = "update_fields"
UPSERT_CONFLICT_FIELDS = "conflict_fields"
