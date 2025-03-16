from __future__ import annotations

from strawchemy import Strawchemy

from .models import Color, Fruit, GeoModel, SQLDataTypes, SQLDataTypesContainer, User

strawchemy = Strawchemy()


@strawchemy.type(Color, include="all", override=True)
class ColorType: ...


@strawchemy.type(Color, include="all", child_pagination=True)
class ColorTypeWithPagination: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.type(Fruit, include="all", override=True)
class FruitType: ...


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


@strawchemy.type(SQLDataTypes, include="all")
class SQLDataTypesType: ...


@strawchemy.type(SQLDataTypesContainer, include="all", override=True)
class SQLDataTypesContainerType: ...


@strawchemy.type(GeoModel, include="all")
class GeoFieldsType: ...


@strawchemy.filter_input(GeoModel, include="all")
class GeoFieldsFilter: ...
