from __future__ import annotations

import strawberry
from strawberry import auto

from strawchemy import Strawchemy
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit)
class FruitTypeCustomName:
    name: int
    color: auto


@strawchemy.type(Color, include="all", scope="schema")
class ColorType:
    fruits: auto
    name: int


@strawberry.type
class Query:
    custom_fruit: FruitTypeCustomName = strawchemy.field()
