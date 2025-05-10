from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all", child_pagination=True)
class FruitType:
    pass


@strawberry.type
class Query:
    fruit: list[FruitType] = strawchemy.field()
