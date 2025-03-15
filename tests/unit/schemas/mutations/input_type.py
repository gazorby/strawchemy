from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.input(SQLDataTypes, include="all")
class SQLDataTypesCreate: ...


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_sql_data_types(self, sql_data_types: SQLDataTypesCreate) -> list[SQLDataTypesType]: ...
