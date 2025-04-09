from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group

strawchemy = Strawchemy()


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawberry.type
class Mutation:
    delete_groups: GroupType = strawchemy.delete()
