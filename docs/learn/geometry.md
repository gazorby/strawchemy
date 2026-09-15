# Geometry

Before any of this works, you need:

- the `geo` extra: `uv add "strawchemy[geo]"`, which brings in [GeoAlchemy2](https://github.com/geoalchemy/geoalchemy2)
- PostgreSQL as the dialect — geometry filters work on no other
- PostGIS enabled in the database: `CREATE EXTENSION IF NOT EXISTS postgis`
- columns declared with GeoAlchemy2's `Geometry` type

## Filtering geometry

Strawchemy supports spatial filtering capabilities for geometry fields
using [GeoJSON](https://datatracker.ietf.org/doc/html/rfc7946). This page defines its own model:

```python
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy.orm import Mapped, mapped_column

from quickstart.models import Base


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

Strawchemy supports the following geo filter operations:

- **containsGeometry**: Filters for geometries that contain the specified GeoJSON geometry
- **withinGeometry**: Filters for geometries that are within the specified GeoJSON geometry
- **isNull**: Filters for null geometry values

These filters work with all geometry types supported by PostGIS, including:

- `Point`
- `LineString`
- `Polygon`
- `MultiPoint`
- `MultiLineString`
- `MultiPolygon`
- `Geometry` (generic geometry type)
