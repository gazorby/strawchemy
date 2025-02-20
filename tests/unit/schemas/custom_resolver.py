from __future__ import annotations

from typing import Any

from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import Info, auto
from tests.models import Color, Fruit

strawchemy = Strawchemy()


@strawchemy.type(Color)
class ColorType:
    id: auto
    name: auto


@strawchemy.type(Fruit, override=True)
class FruitType:
    id: auto
    name: auto

    @strawberry.field
    def color(self, info: Info, root: Any) -> ColorType:
        return root.color


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
