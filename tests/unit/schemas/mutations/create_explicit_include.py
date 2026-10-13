from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Group, TimestampedRecord

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawchemy.type(TimestampedRecord, include="all")
class TimestampedRecordType: ...


@strawchemy.create_input(Group, include=["id", "name", "tag", "users", "color"])
class GroupInput: ...


@strawchemy.create_input(TimestampedRecord, include=["id", "created_at"])
class TimestampedRecordCreateInput: ...


@strawberry.type
class Mutation:
    create_group: GroupType = strawchemy.create(GroupInput)
    create_record: TimestampedRecordType = strawchemy.create(TimestampedRecordCreateInput)
