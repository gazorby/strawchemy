from __future__ import annotations

from sqlalchemy.dialects.postgresql import dialect

from strawchemy.schema.filters.geo import GeoComparison, GeoFilter
from tests.unit.models import GeoModel


def test_geo_filter_is_null_false() -> None:
    expressions = GeoFilter(comparison=GeoComparison(is_null=False)).to_expressions(dialect(), GeoModel.point)

    assert len(expressions) == 1
    assert str(expressions[0]) == "geos_fields.point IS NOT NULL"
