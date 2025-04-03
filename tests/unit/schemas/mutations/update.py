from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group, SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawchemy.input(SQLDataTypes, "update", include="all")
class SQLDataTypesUpdate: ...


@strawchemy.input(Group, "update", include="all")
class GroupUpdate: ...


@strawberry.type
class Mutation:
    update_data_type: SQLDataTypesType = strawchemy.update_mutation(SQLDataTypesUpdate)
    update_data_types: list[SQLDataTypesType] = strawchemy.update_mutation(SQLDataTypesUpdate)

    update_group: GroupType = strawchemy.update_mutation(GroupUpdate)
    update_groups: list[GroupType] = strawchemy.update_mutation(GroupUpdate)
