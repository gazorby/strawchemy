from __future__ import annotations

from strawchemy import ModelInstance, QueryHook, Strawchemy
from strawchemy.sqlalchemy.hook import QueryHookResult

from sqlalchemy import Select
from sqlalchemy.orm.util import AliasedClass
from strawberry import Info

from .models import Color, Fruit, SQLDataTypes, SQLDataTypesContainer, User

strawchemy = Strawchemy()


def _user_fruit_filter(
    statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit], info: Info
) -> QueryHookResult[Fruit]:
    if info.context.role == "user":
        return QueryHookResult(statement=statement.where(alias.name == "Apple"))
    return QueryHookResult(statement=statement)


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

    @strawchemy.field(query_hook=QueryHook(always_load=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return self.instance.description


@strawchemy.type(Fruit, exclude={"color"}, query_hook=_user_fruit_filter)
class FilteredFruitType: ...


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


@strawchemy.order_by_input(SQLDataTypes, include="all")
class SQLDataTypesOrderBy: ...


@strawchemy.type(SQLDataTypes, include="all", override=True)
class SQLDataTypesType: ...


@strawchemy.aggregation_type(SQLDataTypes, include="all")
class SQLDataTypesAggregationType: ...


@strawchemy.type(SQLDataTypesContainer, include="all", override=True)
class SQLDataTypesContainerType: ...


@strawchemy.filter_input(SQLDataTypesContainer, include="all")
class SQLDataTypesContainerFilter: ...


@strawchemy.order_by_input(SQLDataTypesContainer, include="all", override=True)
class SQLDataTypesContainerOrderBy: ...
