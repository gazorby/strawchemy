from __future__ import annotations

from typing import Any

from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import Info, auto
from tests.models import Color, Fruit

strawchemy = Strawchemy()


@strawchemy.type(Fruit)
class FruitType:
    name: int

    @strawberry.field
    def color(self, info: Info, root: Any) -> ColorType:
        return root.color


@strawchemy.type(Color, include="all")
class ColorType:
    id: auto
    name: auto
