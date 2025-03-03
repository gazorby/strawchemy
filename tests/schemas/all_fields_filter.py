from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all")
class FruitType:
    pass


@strawchemy.filter_input(Fruit, include="all")
class FruitFilter:
    pass


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field(filter_input=FruitFilter)
