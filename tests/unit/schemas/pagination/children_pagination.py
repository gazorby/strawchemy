from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all", child_pagination=True)
class FruitType:
    pass


@strawberry.type
class Query:
    fruit: list[FruitType] = strawchemy.field()
