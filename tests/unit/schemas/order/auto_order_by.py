from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group

strawchemy = Strawchemy()


@strawchemy.type(Group, include="all", child_order_by=True)
class GroupType: ...


@strawberry.type
class Query:
    group: list[GroupType] = strawchemy.field()
