from __future__ import annotations

from strawchemy import Strawchemy

from .models import Fruit, User

strawchemy = Strawchemy()


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.type(Fruit, include="all")
class FruitType: ...


@strawchemy.type(Fruit, include="all", child_pagination=True, child_order_by=True)
class FruitTypeWithPaginationAndOrderBy: ...


@strawchemy.filter_input(Fruit, include="all")
class FruitFilter: ...


@strawchemy.filter_input(User, include="all")
class UserFilter: ...


@strawchemy.order_by_input(Fruit, include="all", override=True)
class FruitOrderBy_: ...  # noqa: N801


@strawchemy.order_by_input(User, include="all", override=True)
class UserOrderBy: ...
