import strawberry
from strawberry import auto

from strawchemy import Strawchemy
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include=["id", "name", "color"])
class FruitType:
    name: auto
    secret: strawberry.Private[str]
    color: ColorType  # noqa: F821  # ty: ignore[unresolved-reference]


@strawchemy.type(Color, include=["id", "name"])
class ColorType:
    pass


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
