from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.unit.models import Group, Tag, User

strawchemy = Strawchemy()


@strawchemy.type(Group, include="all", override=True)
class GroupType:
    name: int


@strawchemy.type(User, include="all", override=True)
class UserType:
    name: int


@strawchemy.type(Tag, include="all", override=True)
class TagType:
    name: int


@strawberry.type
class Query:
    user: UserType = strawchemy.field()
    tag: TagType = strawchemy.field()
