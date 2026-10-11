from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Color, include="all")
class ColorType:
    extra: Later | None = None
    extras: list[Later] = strawberry.field(default_factory=list)


@strawberry.type
class Later:
    x: int


@strawberry.type
class Query:
    colors: list[ColorType] = strawchemy.field()
