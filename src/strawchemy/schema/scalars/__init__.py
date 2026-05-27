from __future__ import annotations

from typing import Any

from strawchemy.schema.scalars.base import Date, DateTime, HStore, Interval, Time

__all__ = ("HSTORE_SCALAR_OVERRIDES", "Date", "DateTime", "HStore", "Interval", "Time")

HSTORE_SCALAR_OVERRIDES: dict[object, type[Any]] = {
    dict[str, str]: HStore,
}
