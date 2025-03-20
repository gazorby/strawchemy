from __future__ import annotations

from importlib.util import find_spec

__all__ = ("GEO_INSTALLED",)

GEO_INSTALLED: bool = all(find_spec(package) is not None for package in ("geoalchemy2", "shapely"))
