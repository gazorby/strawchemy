from __future__ import annotations

import strawberry

from tests.unit.schemas.late_type_module.color import ColorType
from tests.unit.schemas.late_type_module.fruit import FruitType, strawchemy

__all__ = ("ColorType", "Query")


@strawberry.type
class Query:
    fruits: list[FruitType] = strawchemy.field()
