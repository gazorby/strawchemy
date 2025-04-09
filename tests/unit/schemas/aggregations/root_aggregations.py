from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import SQLDataTypes

strawchemy = Strawchemy()


@strawchemy.aggregate(SQLDataTypes, include="all")
class SQLDataTypesAggregationType: ...


@strawberry.type
class Query:
    sql_data_types: list[SQLDataTypesAggregationType] = strawchemy.field(root_aggregations=True)
