from __future__ import annotations

from pydantic import BaseModel

from strawchemy import Strawchemy
from tests.unit.models import Color

strawchemy = Strawchemy("postgresql")


@strawchemy.pydantic.create(Color, include=["name"])
class ColorCreate:
    extra: Later | None = None


class Later(BaseModel):
    x: int
