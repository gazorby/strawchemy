from __future__ import annotations

from typing import TYPE_CHECKING

from strawberry import auto  # noqa: TC002  # resolved at runtime by strawchemy

from strawchemy import Strawchemy
from tests.unit.models import Fruit

if TYPE_CHECKING:
    from tests.unit.schemas.late_type_module.color import ColorType

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Fruit, include=["id", "name", "color"])
class FruitType:
    name: auto
    color: ColorType
