from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Color

strawchemy = Strawchemy()


@strawchemy.type(Color, include="all")
class ColorType: ...


@strawchemy.distinct_on(Color, include="all")
class ColorDistinctOnFields: ...


@strawberry.type
class Query:
    color: list[ColorType] = strawchemy.field(distinct_on=ColorDistinctOnFields)
