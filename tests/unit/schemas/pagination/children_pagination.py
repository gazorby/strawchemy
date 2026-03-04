from __future__ import annotations

import strawberry
from strawchemy import Strawchemy
from tests.unit.models import Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all", child_pagination=True)
class FruitType:
    pass


@strawberry.type
class Query:
    fruit: list[FruitType] = strawchemy.field()
