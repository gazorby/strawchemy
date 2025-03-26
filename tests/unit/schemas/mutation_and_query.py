from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all")
class FruitType: ...


@strawchemy.input(Fruit, include="all")
class FruitInput: ...


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
    fruits: list[FruitType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_fruit: FruitType = strawchemy.create_mutation(FruitInput)
    create_fruits: list[FruitType] = strawchemy.create_mutation(FruitInput)
