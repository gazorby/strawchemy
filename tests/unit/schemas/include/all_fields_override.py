from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all")
class FruitType:
    name: int  # override


@strawchemy.type(Color, include="all", override=True)
class ColorType:
    fruits: list[FruitType]


@strawberry.type
class Query:
    fruit: FruitType
