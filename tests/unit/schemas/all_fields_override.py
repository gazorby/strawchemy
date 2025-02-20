from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all")
class FruitType:
    name: int  # override


@strawberry.type
class Query:
    fruit: FruitType
