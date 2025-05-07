from __future__ import annotations

from strawchemy import Strawchemy, StrawchemyConfig

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy(StrawchemyConfig("postgresql", pagination=True))


@strawchemy.type(Fruit, include="all")
class FruitType:
    pass


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
