from __future__ import annotations

from tests.unit.models import Color
from tests.unit.schemas.late_type_module.fruit import strawchemy


@strawchemy.type(Color, include=["id", "name"])
class ColorType:
    pass
