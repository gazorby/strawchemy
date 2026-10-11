# Geometry

Geometry filtering requires:

- the `geo` extra: `uv add "strawchemy[geo]"`, which brings in [GeoAlchemy2](https://github.com/geoalchemy/geoalchemy2)
- PostgreSQL as the dialect — geometry filters work on no other
- PostGIS enabled in the database: `CREATE EXTENSION IF NOT EXISTS postgis`
- columns declared with GeoAlchemy2's `Geometry` type

## Filtering geometry

Geometry fields accept spatial filters expressed in [GeoJSON](https://datatracker.ietf.org/doc/html/rfc7946). This page defines its own model:

```python
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy.orm import Mapped, mapped_column

from quickstart.models import Base
from strawchemy.schema.scalars.geo import GEO_SCALAR_OVERRIDES


class GeoModel(Base):
    __tablename__ = "geo"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    point: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    polygon: Mapped[WKBElement | None] = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)


@strawchemy.type(GeoModel, include="all")
class GeoType: ...


@strawchemy.filter(GeoModel, include="all")
class GeoFieldsFilter: ...


@strawberry.type
class Query:
    geo: list[GeoType] = strawchemy.field(filter_input=GeoFieldsFilter)


schema = strawberry.Schema(query=Query, scalar_overrides=GEO_SCALAR_OVERRIDES)
```

```graphql
# Find geometries that contain a point
{
    geo(filter: { polygon: { containsGeometry: { type: "Point", coordinates: [0.5, 0.5] } } }) {
        id
        polygon
    }
}
```

```graphql
# Find geometries that are within a polygon
{
    geo(filter: { point: { withinGeometry: { type: "Polygon", coordinates: [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]] } } }) {
        id
        point
    }
}
```

```graphql
# Find records with null geometry
{
    geo(filter: { point: { isNull: true } }) {
        id
    }
}
```

## Operations

Strawchemy supports three geo filter operations:

- **containsGeometry**: Filters for geometries that contain the specified GeoJSON geometry
- **withinGeometry**: Filters for geometries within the specified GeoJSON geometry
- **isNull**: Filters for null (`true`) or non-null (`false`) geometry values

These filters work with every geometry type PostGIS supports, including:

- `Point`
- `LineString`
- `Polygon`
- `MultiPoint`
- `MultiLineString`
- `MultiPolygon`
- `GeometryCollection`
- `Geometry` (generic geometry type)
