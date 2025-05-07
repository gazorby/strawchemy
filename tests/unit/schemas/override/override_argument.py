from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all", child_pagination=True, child_order_by=True)
class FruitType:
    name: int


@strawchemy.order(Fruit, include="all", override=True)
class FruitOrderBy:
    override: bool = True


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field(order_by=FruitOrderBy)
