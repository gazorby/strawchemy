from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import TableMappedFruit

strawchemy = Strawchemy("postgresql")


@strawchemy.type(TableMappedFruit, include="all")
class TableMappedFruitType: ...


@strawchemy.create_input(TableMappedFruit, include="all")
class TableMappedFruitCreate: ...


@strawchemy.pk_update_input(TableMappedFruit, include="all")
class TableMappedFruitPkUpdate: ...


@strawchemy.filter_update_input(TableMappedFruit, include="all")
class TableMappedFruitFilterUpdate: ...


@strawchemy.filter(TableMappedFruit, include="all")
class TableMappedFruitFilter: ...


@strawberry.type
class Mutation:
    create_fruit: TableMappedFruitType = strawchemy.create(TableMappedFruitCreate)
    update_fruits_by_ids: list[TableMappedFruitType] = strawchemy.update_by_ids(TableMappedFruitPkUpdate)
    update_fruits: list[TableMappedFruitType] = strawchemy.update(TableMappedFruitFilterUpdate, TableMappedFruitFilter)
