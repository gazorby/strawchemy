from __future__ import annotations

import strawberry
from strawchemy import Strawchemy
from tests.unit.models import Group

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Group, include="all", child_order_by=True)
class GroupType: ...


@strawberry.type
class Query:
    group: list[GroupType] = strawchemy.field()
