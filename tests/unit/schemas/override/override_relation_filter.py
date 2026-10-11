from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color, Container, Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all")
class FruitType: ...


@strawchemy.filter(Color, include="all")
class ColorFilter: ...


@strawchemy.type(Color, include="all", filter_input=ColorFilter, override=True)
class ColorType: ...


@strawchemy.type(Container, include={"colors"})
class ContainerType: ...


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
    containers: list[ContainerType] = strawchemy.field()
