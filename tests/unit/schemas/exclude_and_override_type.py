from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, exclude=["name"])
class FruitType:
    sweetness: str


@strawberry.type
class Query:
    fruit: FruitType
