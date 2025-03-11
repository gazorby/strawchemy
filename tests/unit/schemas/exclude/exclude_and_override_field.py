from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import auto
from tests.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, exclude=["name"])
class FruitType:
    name: auto


@strawberry.type
class Query:
    fruit: FruitType
