from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Group, Tag, User

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Group, include="all", scope="schema")
class GroupType:
    name: int


@strawchemy.type(User, include="all", scope="schema")
class UserType:
    name: int


@strawchemy.type(Tag, include="all", scope="schema")
class TagType:
    name: int


@strawberry.type
class Query:
    user: UserType = strawchemy.field()
    tag: TagType = strawchemy.field()
