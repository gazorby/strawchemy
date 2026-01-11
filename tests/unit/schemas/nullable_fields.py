from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import NullableTestModel

strawchemy = Strawchemy("postgresql")


@strawchemy.type(NullableTestModel, include="all")
class NullableTestModelType:
    pass


@strawberry.type
class Query:
    nullable_test: NullableTestModelType
