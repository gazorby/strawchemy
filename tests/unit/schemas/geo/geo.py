from __future__ import annotations

from strawchemy.mapper import Strawchemy

import strawberry
from tests.unit.models import GeoModel

strawchemy = Strawchemy()


@strawchemy.type(GeoModel, include="all")
class GeosFieldsType: ...


@strawberry.type
class Query:
    geo: GeosFieldsType
