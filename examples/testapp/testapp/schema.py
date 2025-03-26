from __future__ import annotations

import strawberry

from .types import ColorInput, ColorType, FruitInput, FruitType, strawchemy


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
    fruits: list[FruitType] = strawchemy.field()

    color: ColorType = strawchemy.field()
    colors: list[ColorType] = strawchemy.field()


@strawberry.type
class Mutation:
    create_fruit: FruitType = strawchemy.create_mutation(FruitInput)
    create_fruits: list[FruitType] = strawchemy.create_mutation(FruitInput)

    create_color: ColorType = strawchemy.create_mutation(ColorInput)
    create_colors: list[ColorType] = strawchemy.create_mutation(ColorInput)


schema = strawberry.Schema(query=Query, mutation=Mutation)
