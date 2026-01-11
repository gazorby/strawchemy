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

LIMIT_KEY: str = "limit"
OFFSET_KEY: str = "offset"
ORDER_BY_KEY: str = "order_by"
FILTER_KEY: str = "filter"
DISTINCT_ON_KEY: str = "distinct_on"

AGGREGATIONS_KEY: str = "aggregations"
NODES_KEY: str = "nodes"

DATA_KEY: str = "data"
JSON_PATH_KEY: str = "path"

UPSERT_UPDATE_FIELDS: str = "update_fields"
UPSERT_CONFLICT_FIELDS: str = "conflict_fields"
