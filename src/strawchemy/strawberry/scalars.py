from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from functools import partial
from typing import NewType

from msgspec import json

from strawberry import scalar
from strawberry.schema.types.base_scalars import wrap_parser

__all__ = ("Interval", "Time")


def _serialize_time(value: time | timedelta) -> str:
    if isinstance(value, timedelta):
        value = (datetime.min.replace(tzinfo=UTC) + value).time()
    return value.isoformat()


Interval = scalar(
    NewType("Interval", timedelta),
    description=(
        "The `Interval` scalar type represents a duration of time as specified by "
        "[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Durations)."
    ),
    parse_value=partial(json.decode, type=timedelta),
    serialize=json.encode,
    specified_by_url="https://en.wikipedia.org/wiki/ISO_8601#Durations",
)

Time = scalar(NewType("Time", time), serialize=_serialize_time, parse_value=wrap_parser(time.fromisoformat, "Time"))
