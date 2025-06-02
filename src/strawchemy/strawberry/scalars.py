from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from typing import NewType

from msgspec import json

from strawberry import scalar
from strawberry.schema.types.base_scalars import wrap_parser

__all__ = ("Date", "DateTime", "Interval", "Time")


def _serialize_time(value: time | timedelta | str) -> str:
    if isinstance(value, timedelta):
        value = (datetime.min.replace(tzinfo=UTC) + value).time()
    return value if isinstance(value, str) else value.isoformat()


def _serialize_date(value: date | datetime | str) -> str:
    return value.isoformat() if isinstance(value, date | datetime) else value


def _serialize(value: timedelta) -> str:
    return json.encode(value).decode()


Interval = scalar(
    NewType("Interval", timedelta),
    description=(
        "The `Interval` scalar type represents a duration of time as specified by "
        "[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Durations)."
    ),
    parse_value=partial(json.decode, type=timedelta),
    serialize=_serialize,
    specified_by_url="https://en.wikipedia.org/wiki/ISO_8601#Durations",
)

Time = scalar(
    NewType("Time", time),
    serialize=_serialize_time,
    parse_value=wrap_parser(time.fromisoformat, "Time"),
    description="Time (isoformat)",
)
Date = scalar(NewType("Date", date), serialize=_serialize_date, parse_value=wrap_parser(date.fromisoformat, "Date"))
DateTime = scalar(
    NewType("DateTime", datetime),
    serialize=_serialize_date,
    parse_value=wrap_parser(datetime.fromisoformat, "DateTime"),
)
