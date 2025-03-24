from __future__ import annotations

from strawchemy import LoadColumnsHook, Strawchemy

import strawberry
from strawberry import auto
from tests.unit.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, query_hook=LoadColumnsHook(columns=[Fruit.color]))
class FruitType:
    family: auto


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
