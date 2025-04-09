from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group, SQLDataTypes, Tag

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawchemy.type(Tag, include="all", override=True)
class TagType: ...


@strawchemy.update_input(SQLDataTypes, include="all")
class SQLDataTypesUpdate: ...


@strawchemy.update_input(Group, include="all")
class GroupUpdate: ...


@strawchemy.update_input(Tag, include="all")
class TagUpdate: ...


@strawberry.type
class Mutation:
    update_data_type: SQLDataTypesType = strawchemy.update_by_ids(SQLDataTypesUpdate)
    update_data_types: list[SQLDataTypesType] = strawchemy.update_by_ids(SQLDataTypesUpdate)

    update_group: GroupType = strawchemy.update_by_ids(GroupUpdate)
    update_groups: list[GroupType] = strawchemy.update_by_ids(GroupUpdate)

    update_tag: TagType = strawchemy.update_by_ids(TagUpdate)
