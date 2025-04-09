from __future__ import annotations

from strawchemy import Strawchemy

from .models import GeoModel

strawchemy = Strawchemy()


@strawchemy.type(GeoModel, include="all")
class GeoFieldsType: ...


@strawchemy.filter(GeoModel, include="all")
class GeoFieldsFilter: ...
