from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import auto
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy()


@strawchemy.type(Color, include="all", override=True)
class ColorType:
    fruits: auto
    name: int


@strawchemy.type(Fruit, include="all", override=True)
class FruitType:
    name: int


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
