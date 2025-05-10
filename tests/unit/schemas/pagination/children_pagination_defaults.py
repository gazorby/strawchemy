from __future__ import annotations

from strawchemy import Strawchemy
from strawchemy.types import DefaultOffsetPagination

import strawberry
from tests.unit.models import Fruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all", child_pagination=DefaultOffsetPagination(limit=10, offset=10))
class FruitType:
    pass


@strawberry.type
class Query:
    fruit_with_default_limit: list[FruitType] = strawchemy.field()
