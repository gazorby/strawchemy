from __future__ import annotations

from strawchemy import Strawchemy

import strawberry
from tests.unit.models import GeoModel

strawchemy = Strawchemy("postgresql")


@strawchemy.type(GeoModel, include="all")
class GeosFieldsType: ...


@strawberry.type
class Query:
    geo: GeosFieldsType
