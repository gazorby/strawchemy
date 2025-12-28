from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Group

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Group, include="all", order="all")
class GroupType: ...


@strawberry.type
class Query:
    group: list[GroupType] = strawchemy.field()
