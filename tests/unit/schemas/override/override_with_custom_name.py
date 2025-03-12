from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import auto
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, override=True)
class FruitTypeCustomName:
    name: int
    color: auto


@strawchemy.type(Color, include="all", override=True)
class ColorType:
    fruits: auto
    name: int


@strawberry.type
class Query:
    custom_fruit: FruitTypeCustomName = strawchemy.field()
