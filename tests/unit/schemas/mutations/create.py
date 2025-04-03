from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import Group, SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.type(Group, include="all")
class GroupType: ...


@strawchemy.input(SQLDataTypes, "create", include="all")
class SQLDataTypesCreate: ...


@strawchemy.input(Group, "create", include="all")
class GroupInput: ...


@strawberry.type
class Mutation:
    create_data_type: SQLDataTypesType = strawchemy.create_mutation(SQLDataTypesCreate)
    create_data_types: list[SQLDataTypesType] = strawchemy.create_mutation(SQLDataTypesCreate)

    create_group: GroupType = strawchemy.create_mutation(GroupInput)
    create_groups: list[GroupType] = strawchemy.create_mutation(GroupInput)
