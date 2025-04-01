from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.input(SQLDataTypes, "create", include="all")
class SQLDataTypesCreate: ...


@strawberry.type
class Mutation:
    create_data_type: SQLDataTypesType = strawchemy.create_mutation(SQLDataTypesCreate)
    create_data_types: list[SQLDataTypesType] = strawchemy.create_mutation(SQLDataTypesCreate)
