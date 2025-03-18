from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.unit.models import Color

strawchemy = Strawchemy()


@strawchemy.type(Color)
class ColorType:
    name: strawberry.auto


@strawberry.type
class Query:
    color_aggregations: list[ColorType] = strawchemy.field(root_aggregations=True)
