from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import NewType

from pydantic import TypeAdapter

from strawberry import scalar

__all__ = ("Interval",)

_IntervalType = TypeAdapter(timedelta)

Interval = scalar(
    NewType("Interval", timedelta),
    description=(
        "The `Interval` scalar type represents a duration of time as specified by "
        "[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Durations)."
    ),
    parse_value=_IntervalType.validate_python,
    serialize=partial(_IntervalType.dump_python, mode="json"),
    specified_by_url="https://en.wikipedia.org/wiki/ISO_8601#Durations",
)
