from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit, include="all")
class FruitType: ...


@strawchemy.type(Color, include="all", override=True)
class ColorType: ...


@strawchemy.input(Fruit, "create", include="all")
class FruitInput: ...


@strawchemy.input(Color, "create", include="all", override=True)
class ColorInput: ...


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
