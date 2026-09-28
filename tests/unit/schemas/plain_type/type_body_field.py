import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color

strawchemy = Strawchemy("postgresql")


@strawberry.type
class Plain:
    name: str


@strawchemy.type(Color, include=["name"])
class ColorType:
    plain: list[Plain] = strawchemy.field()
