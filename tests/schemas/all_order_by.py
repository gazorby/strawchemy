from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all")
class FruitType:
    pass


@strawchemy.order_by_input(Fruit, include="all")
class FruitOrderBy:
    pass


@strawberry.type
class Query:
    fruit: list[FruitType] = strawchemy.field(order_by=FruitOrderBy)
