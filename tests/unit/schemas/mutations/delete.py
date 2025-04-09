from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group

strawchemy = Strawchemy()


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawchemy.filter_input(Group, include="all")
class GroupFilter: ...


@strawberry.type
class Mutation:
    delete_groups: list[GroupType] = strawchemy.delete_mutation()
    delete_groups_filter: list[GroupType] = strawchemy.delete_mutation(GroupFilter)
