from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy("postgresql")


@strawberry.interface
class Named:
    name: str


@strawchemy.type(Color, include={"id", "name"})
class ShadeType(Named):
    pass


@strawchemy.filter(Fruit, include="all")
class FruitFilter: ...


@strawchemy.order(Fruit, include="all")
class FruitOrderBy: ...


@strawchemy.type(Fruit, include={"id", "name"}, filter_input=FruitFilter, order=FruitOrderBy)
class FruitType(Named):
    color: ShadeType


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
    shades: list[ShadeType] = strawchemy.field()
