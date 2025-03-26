from __future__ import annotations

import strawberry

from .types import ColorType, FruitInput, FruitType, strawchemy


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field(name="bar")
    fruits: list[FruitType] = strawchemy.field()

    color: ColorType = strawchemy.field()
    colors: list[ColorType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_fruit: FruitType = strawchemy.create_mutation(FruitInput)
    create_fruits: list[FruitType] = strawchemy.create_mutation(FruitInput)


schema = strawberry.Schema(query=Query)
