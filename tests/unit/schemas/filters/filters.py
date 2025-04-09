from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.filter(SQLDataTypes, include="all")
class SQLDataTypesFilter: ...


@strawberry.type
class Query:
    sql_data_types: list[SQLDataTypesType] = strawchemy.field(filter_input=SQLDataTypesFilter)
