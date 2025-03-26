from __future__ import annotations

from strawchemy import Strawchemy

from .models import Color, Fruit

strawchemy = Strawchemy()

# Filter


@strawchemy.filter_input(Fruit, include="all")
class FruitFilter: ...


@strawchemy.filter_input(Color, include="all")
class ColorFilter: ...


# Order


@strawchemy.order_by_input(Fruit, include="all")
class FruitOrder: ...


@strawchemy.order_by_input(Color, include="all")
class ColorOrder: ...


# types


@strawchemy.type(Fruit, include="all", filter_input=FruitFilter, order_by=FruitOrder, override=True)
class FruitType: ...


@strawchemy.type(Color, include="all", filter_input=ColorFilter, order_by=ColorOrder, override=True)
class ColorType: ...


# Input types


@strawchemy.input(Fruit, include="all")
class FruitInput: ...


@strawchemy.input(Color, include="all")
class ColorInput: ...
