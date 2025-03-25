from __future__ import annotations

from typing import override

from strawchemy import ModelInstance, QueryHook, Strawchemy

from sqlalchemy import Select
from sqlalchemy.orm.util import AliasedClass

from .models import Color, Fruit, SQLDataTypes, SQLDataTypesContainer, User

strawchemy = Strawchemy()


class FruitFilterHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit]) -> Select[tuple[Fruit]]:
        if self.info.context.role == "user":
            return statement.where(alias.name == "Apple")
        return statement


class FruitOrderingHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit]) -> Select[tuple[Fruit]]:
        return statement.order_by(alias.name.asc())


@strawchemy.type(Color, include="all", override=True)
class ColorType: ...


@strawchemy.type(Color, include="all", child_pagination=True)
class ColorTypeWithPagination: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.type(Fruit, include="all", override=True)
class FruitType: ...


@strawchemy.type(Fruit, exclude={"color"})
class FruitTypeWithDescription:
    instance: ModelInstance[Fruit]

    @strawchemy.field(query_hook=QueryHook(load_columns=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return self.instance.description

    @strawchemy.field(query_hook=QueryHook(load_columns=[]))
    def empty_query_hook(self) -> str:
        return "success"


@strawchemy.type(Fruit, exclude={"color"}, query_hook=FruitFilterHook())
class FilteredFruitType: ...


@strawchemy.type(Fruit, exclude={"color"}, query_hook=FruitOrderingHook())
class OrderedFruitType: ...


@strawchemy.aggregation_type(Fruit, include="all")
class FruitAggregationType: ...


@strawchemy.type(Fruit, include="all", child_pagination=True, child_order_by=True)
class FruitTypeWithPaginationAndOrderBy: ...


@strawchemy.filter_input(Fruit, include="all")
class FruitFilter: ...


@strawchemy.filter_input(User, include="all")
class UserFilter: ...


@strawchemy.order_by_input(Fruit, include="all", override=True)
class FruitOrderBy: ...


@strawchemy.order_by_input(User, include="all", override=True)
class UserOrderBy: ...


@strawchemy.filter_input(SQLDataTypes, include="all")
class SQLDataTypesFilter: ...


@strawchemy.order_by_input(SQLDataTypes, include="all", override=True)
class SQLDataTypesOrderBy: ...


@strawchemy.type(SQLDataTypes, include="all", override=True)
class SQLDataTypesType: ...


@strawchemy.aggregation_type(SQLDataTypes, include="all")
class SQLDataTypesAggregationType: ...


@strawchemy.type(SQLDataTypesContainer, include="all", override=True, child_order_by=True)
class SQLDataTypesContainerType: ...


@strawchemy.filter_input(SQLDataTypesContainer, include="all")
class SQLDataTypesContainerFilter: ...


@strawchemy.order_by_input(SQLDataTypesContainer, include="all", override=True)
class SQLDataTypesContainerOrderBy: ...
