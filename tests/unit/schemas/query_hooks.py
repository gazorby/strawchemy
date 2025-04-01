from __future__ import annotations

from strawchemy import QueryHook, Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, query_hook=QueryHook(load=[(Fruit.name, (Fruit.id,))]))
class FruitType: ...


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
