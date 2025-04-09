from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.filter(SQLDataTypes, include="all")
class SQLDataTypesFilter: ...


@strawchemy.type(SQLDataTypes, include="all", filter_input=SQLDataTypesFilter)
class SQLDataTypesType: ...


@strawberry.type
class Query:
    sql_data_types: list[SQLDataTypesType] = strawchemy.field()
