from __future__ import annotations

from strawchemy.config import StrawchemyConfig
from strawchemy.mapper import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy(StrawchemyConfig(pagination=True))


@strawchemy.type(Fruit, include="all")
class FruitType:
    pass


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
