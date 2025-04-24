from __future__ import annotations

from typing import Annotated, override

from pydantic import AfterValidator
from strawchemy import ModelInstance, QueryHook, Strawchemy

from sqlalchemy import Select
from sqlalchemy.orm.util import AliasedClass

from .models import Color, Fruit, FruitFarm, RankedUser, SQLDataTypes, SQLDataTypesContainer, User

strawchemy = Strawchemy()


def _check_lower_case(value: str) -> str:
    if not value.islower():
        msg = "Name must be lower cased"
        raise ValueError(msg)
    return value


# Hooks


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


# User


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.order(User, include="all", override=True)
class UserOrderBy: ...


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.create_input(User, include="all")
class UserCreate: ...


@strawchemy.pk_update_input(User, include="all")
class UserUpdateInput: ...


# Fruit


@strawchemy.type(Fruit, include="all", override=True)
class FruitType: ...


@strawchemy.type(Fruit, exclude={"color"})
class FruitTypeHooks:
    instance: ModelInstance[Fruit]

    @strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return self.instance.description

    @strawchemy.field(query_hook=QueryHook())
    def empty_query_hook(self) -> str:
        return "success"

    @strawchemy.field(query_hook=QueryHook(load=[(Fruit.color, [Color.name, Color.created_at])]))
    def pretty_color(self) -> str:
        return f"Color is {self.instance.color.name}" if self.instance.color else "No color!"

    @strawchemy.field(query_hook=QueryHook(load=[Fruit.farms]))
    def pretty_farms(self) -> str:
        return (
            f"Farms are: {', '.join(farm.name for farm in self.instance.farms)}" if self.instance.farms else "No farm!"
        )


@strawchemy.type(Fruit, exclude={"color"}, query_hook=FruitFilterHook())
class FilteredFruitType: ...


@strawchemy.type(Fruit, exclude={"color"}, query_hook=FruitOrderingHook())
class OrderedFruitType: ...


@strawchemy.aggregate(Fruit, include="all")
class FruitAggregationType: ...


@strawchemy.type(Fruit, include="all", child_pagination=True, child_order_by=True)
class FruitTypeWithPaginationAndOrderBy: ...


@strawchemy.filter(Fruit, include="all")
class FruitFilter: ...


@strawchemy.order(Fruit, include="all", override=True)
class FruitOrderBy: ...


@strawchemy.create_input(Fruit, include="all")
class FruitCreateInput: ...


@strawchemy.pk_update_input(Fruit, include="all")
class FruitUpdateInput: ...


# Color


@strawchemy.type(Color, include="all", override=True)
class ColorType: ...


@strawchemy.distinct_on(Color, include="all", override=True)
class ColorDistinctOn: ...


@strawchemy.type(Color, include="all", child_pagination=True)
class ColorTypeWithPagination: ...


@strawchemy.type(Color, include="all")
class ColorWithFilteredFruit:
    instance: ModelInstance[Color]

    fruits: list[FilteredFruitType]

    @strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [(Fruit.farms, [FruitFarm.name])])]))
    def farms(self) -> str:
        return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"


@strawchemy.type(Color, include="all")
class ColorTypeHooks:
    instance: ModelInstance[Color]

    fruits: list[FruitTypeHooks]


@strawchemy.create_input(Color, include="all")
class ColorCreateInput: ...


@strawchemy.create_input(RankedUser, include="all")
class RankedUserCreateInput: ...


@strawchemy.type(RankedUser, include="all")
class RankedUserType: ...


@strawchemy.pydantic.create(RankedUser, include="all")
class RankedUserCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pydantic.create(Color, include="all")
class ColorCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pydantic.pk_update(Color, include="all")
class ColorPkUpdateValidation: ...


@strawchemy.pydantic.filter_update(Color, include="all")
class ColorFilterUpdateValidation: ...


@strawchemy.pk_update_input(Color, include="all")
class ColorUpdateInput: ...


@strawchemy.filter_update_input(Color, include="all")
class ColorPartial: ...


@strawchemy.filter(Color, include="all")
class ColorFilter: ...


# SQL Data types


@strawchemy.filter(SQLDataTypes, include="all")
class SQLDataTypesFilter: ...


@strawchemy.order(SQLDataTypes, include="all", override=True)
class SQLDataTypesOrderBy: ...


@strawchemy.type(SQLDataTypes, include="all", override=True)
class SQLDataTypesType: ...


@strawchemy.aggregate(SQLDataTypes, include="all")
class SQLDataTypesAggregationType: ...


# SQL Data types Container


@strawchemy.type(SQLDataTypesContainer, include="all", override=True, child_order_by=True)
class SQLDataTypesContainerType: ...


@strawchemy.filter(SQLDataTypesContainer, include="all")
class SQLDataTypesContainerFilter: ...


@strawchemy.order(SQLDataTypesContainer, include="all", override=True)
class SQLDataTypesContainerOrderBy: ...
