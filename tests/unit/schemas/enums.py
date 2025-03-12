from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from strawberry import auto
from tests.unit.models import Vegetable

strawchemy = Strawchemy()


@strawchemy.type(Vegetable)
class VegetableType:
    family: auto


@strawberry.type
class Query:
    vegetable: VegetableType = strawchemy.field()
