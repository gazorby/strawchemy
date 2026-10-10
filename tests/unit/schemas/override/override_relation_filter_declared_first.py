from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color, Container

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Container, include={"colors"})
class ContainerType: ...


@strawchemy.filter(Color, include="all")
class ColorFilter: ...


@strawchemy.type(Color, include="all", filter_input=ColorFilter, override=True)
class ColorType: ...


@strawberry.type
class Query:
    containers: list[ContainerType] = strawchemy.field()
