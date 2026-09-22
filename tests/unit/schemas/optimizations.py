"""DB-free strawchemy schema over unit ``Color``/``Fruit``/``Group`` for optimization tests.

Built with the ``postgresql`` dialect, but executed under each runtime dialect: the
transpiler re-reads the runtime dialect name at execution time, so the same static
schema emits dialect-specific SQL. The aggregation functions exercised
(count/avg/sum/max) exist in every supported dialect's feature set.
"""

from __future__ import annotations

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Color, Fruit, Group

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include="all", override=True)
class FruitType: ...


@strawchemy.type(Color, include="all", order="all", override=True)
class ColorType: ...


@strawchemy.filter(Color, include="all")
class ColorFilter: ...


@strawchemy.order(Color, include="all")
class ColorOrder: ...


@strawchemy.type(Group, include="all", override=True)
class GroupType: ...


@strawchemy.filter(Group, include="all")
class GroupFilter: ...


@strawberry.type
class Query:
    colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter, order_by_input=ColorOrder)
    colors_paginated: list[ColorType] = strawchemy.field(
        filter_input=ColorFilter, order_by_input=ColorOrder, pagination=True
    )
    groups: list[GroupType] = strawchemy.field(filter_input=GroupFilter)


schema = strawberry.Schema(query=Query)
