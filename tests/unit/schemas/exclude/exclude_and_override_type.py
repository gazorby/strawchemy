from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, exclude=["name"])
class FruitType:
    sweetness: str


@strawberry.type
class Query:
    fruit: FruitType
