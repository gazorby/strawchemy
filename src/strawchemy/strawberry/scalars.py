from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import partial
from typing import NewType, TypeVar

from msgspec import json
from strawberry.schema.types.base_scalars import wrap_parser

from strawberry import scalar

__all__ = ("Date", "DateTime", "Interval", "Time")

UTC = timezone.utc

T = TypeVar("T")


def _serialize_time(value: time | timedelta | str) -> str:
    if isinstance(value, timedelta):
        value = (datetime.min.replace(tzinfo=UTC) + value).time()
    return value if isinstance(value, str) else value.isoformat()


def _serialize_date(value: date | datetime | str) -> str:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _serialize(value: timedelta) -> str:
    return json.encode(value).decode()


def new_type(name: str, type_: type[T]) -> type[T]:
    # Needed for pyright
    return NewType(name, type_)  # pyright: ignore[reportArgumentType]


Interval = scalar(
    new_type("Interval", timedelta),
    description=(
        "The `Interval` scalar type represents a duration of time as specified by "
        "[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Durations)."
    ),
    parse_value=partial(json.decode, type=timedelta),
    serialize=_serialize,
    specified_by_url="https://en.wikipedia.org/wiki/ISO_8601#Durations",
)

Time = scalar(
    new_type("Time", time),
    serialize=_serialize_time,
    parse_value=wrap_parser(time.fromisoformat, "Time"),
    description="Time (isoformat)",
)
Date = scalar(new_type("Date", date), serialize=_serialize_date, parse_value=wrap_parser(date.fromisoformat, "Date"))
DateTime = scalar(
    new_type("DateTime", datetime),
    serialize=_serialize_date,
    parse_value=wrap_parser(datetime.fromisoformat, "DateTime"),
)
