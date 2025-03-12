from __future__ import annotations

from typing import Any

from strawchemy.config import StrawchemyConfig
from strawchemy.mapper import Strawchemy

import strawberry
from strawberry import Info, auto
from tests.unit.models import Color, Fruit

strawchemy = Strawchemy(StrawchemyConfig(default_id_field_name="pk"))


@strawchemy.type(Color)
class ColorType:
    id: auto
    name: auto


@strawchemy.type(Fruit, include=["name"])
class FruitType:
    @strawberry.field
    def color(self, info: Info, root: Any) -> ColorType:
        return root.color


@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
