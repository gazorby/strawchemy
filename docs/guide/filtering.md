# Filtering

Strawchemy provides powerful filtering capabilities.

<details>
<summary>Filtering example</summary>

First, create a filter input type:

```python
@strawchemy.filter(User, include="all")
class UserFilter:
    pass
```

Then use it in your field:

```python
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

Now you can use various filter operations in your GraphQL queries:

```graphql
{
    # Equality filter
    users(filter: { name: { eq: "John" } }) {
        id
        name
    }

    # Comparison filters
    users(filter: { age: { gt: 18, lte: 30 } }) {
        id
        name
        age
    }

    # String filters
    users(filter: { name: { contains: "oh", ilike: "%OHN%" } }) {
        id
        name
    }

    # Logical operators
    users(filter: { _or: [{ name: { eq: "John" } }, { name: { eq: "Jane" } }] }) {
        id
        name
    }
    # Nested filters
    users(filter: { posts: { title: { contains: "GraphQL" } } }) {
        id
        name
        posts {
            id
            title
        }
    }

    # Compare interval component
    tasks(filter: { duration: { days: { gt: 2 } } }) {
        id
        name
        duration
    }

    # Direct interval comparison
    tasks(filter: { duration: { gt: "P2DT5H" } }) {
        id
        name
        duration
    }
}
```

</details>

Strawchemy supports a wide range of filter operations:

| Data Type/Category                      | Filter Operations                                                                                                                                                                |
|-----------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Common to most types**                | `eq`, `neq`, `isNull`, `in`, `nin`                                                                                                                                               |
| **Numeric types (Int, Float, Decimal)** | `gt`, `gte`, `lt`, `lte`                                                                                                                                                         |
| **String**                              | order filter, plus `like`, `nlike`, `ilike`, `nilike`, `regexp`, `iregexp`, `nregexp`, `inregexp`, `startswith`, `endswith`, `contains`, `istartswith`, `iendswith`, `icontains` |
| **JSON**                                | `contains`, `containedIn`, `hasKey`, `hasKeyAll`, `hasKeyAny`                                                                                                                    |
| **Array**                               | `contains`, `containedIn`, `overlap`                                                                                                                                             |
| **Date**                                | order filters on plain dates, plus `year`, `month`, `day`, `weekDay`, `week`, `quarter`, `isoYear` and `isoWeekDay` filters                                                      |
| **DateTime**                            | All Date filters plus `hour`, `minute`, `second`                                                                                                                                 |
| **Time**                                | order filters on plain times, plus `hour`, `minute` and `second` filters                                                                                                         |
| **Interval**                            | order filters on plain intervals, plus `days`, `hours`, `minutes` and `seconds` filters                                                                                          |
| **Logical**                             | `_and`, `_or`, `_not`                                                                                                                                                            |

## Geo Filters

Strawchemy supports spatial filtering capabilities for geometry fields
using [GeoJSON](https://datatracker.ietf.org/doc/html/rfc7946). To use geo filters, you need to have PostGIS installed
and enabled in your PostgreSQL database.

<details>
<summary>Geo filters example</summary>

Define models and types:

```python
class GeoModel(Base):
    __tablename__ = "geo"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Define geometry columns using GeoAlchemy2
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

Then you can use the following geo filter operations in your GraphQL queries:

```graphql
{
    # Find geometries that contain a point
    geo(
        filter: {
            polygon: { containsGeometry: { type: "Point", coordinates: [0.5, 0.5] } }
        }
    ) {
        id
        polygon
    }

    # Find geometries that are within a polygon
    geo(
        filter: {
            point: {
                withinGeometry: {
                    type: "Polygon"
                    coordinates: [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]]
                }
            }
        }
    ) {
        id
        point
    }

    # Find records with null geometry
    geo(filter: { point: { isNull: true } }) {
        id
    }
}
```

</details>

Strawchemy supports the following geo filter operations:

- **containsGeometry**: Filters for geometries that contain the specified GeoJSON geometry
- **withinGeometry**: Filters for geometries that are within the specified GeoJSON geometry
- **isNull**: Filters for null or non-null geometry values

These filters work with all geometry types supported by PostGIS, including:

- `Point`
- `LineString`
- `Polygon`
- `MultiPoint`
- `MultiLineString`
- `MultiPolygon`
- `Geometry` (generic geometry type)

## Fine-grained filters

By default, `@strawchemy.filter` exposes every operator for every included column. Adding a class body lets you
override what the decorator generated, field by field: restrict a column to specific operators, replace it with a
custom virtual filter, or force-include a field the decorator's `include`/`exclude` would otherwise drop.

<details>
<summary>Fine-grained filter example</summary>

```python
from typing import Any

from sqlalchemy import Select
from strawchemy import TextComparison


def _fruit_sweeter_than(statement: Select[tuple[Fruit]], value: int, **_ctx: Any) -> Select[tuple[Fruit]]:
    return statement.where(Fruit.sweetness >= value)


@strawchemy.filter(Fruit, include=["id", "name", "sweetness"], name="FruitFineGrainedFilter")
class FruitFineGrainedFilter:
    # Only `eq` and `like` are exposed; every other TextComparison operator (`contains`, `gt`, ...) is dropped.
    name: TextComparison = strawchemy.filter_field(ops=["eq", "like"])
    # A virtual filter: no `sweeter_than` column exists on `Fruit`.
    sweeter_than: int = strawchemy.filter_field(apply=_fruit_sweeter_than)
    # Same callable, folded back with an `IN` on the primary key instead of the default correlated `EXISTS`.
    sweeter_than_in: int = strawchemy.filter_field(apply=_fruit_sweeter_than, join="in")


@strawberry.type
class Query:
    fruits_fine_grained: list[FruitType] = strawchemy.field(filter_input=FruitFineGrainedFilter)
```

```graphql
{
    fruitsFineGrained(filter: { name: { eq: "Apple" } }) {
        id
        name
    }

    fruitsFineGrained(filter: { sweeterThan: 5 }) {
        id
        sweetness
    }
}
```

</details>

`strawchemy.filter_field()` accepts:

- **`ops`**: restricts the field to the given comparison operators. Operators left out are absent from the generated
  GraphQL input, so using one is a GraphQL validation error rather than a runtime one.
- **`apply`**: replaces the field with a custom virtual scalar filter. The callable's signature is
  `(statement, value, *, dialect, model) -> Select`: it receives an isolated `select(model)` statement and the
  GraphQL-supplied value, and must only add `.where(...)` predicates to it. It must not join or subquery against
  the same model — the statement is later re-aliased and correlated back to the outer query by primary key, and a
  self-join there could be rewritten ambiguously. `join` picks that correlation strategy: `"exists"` (the default)
  wraps it in a correlated `EXISTS`; `"in"` folds it back with an `IN` against the primary key instead.
- A bare `strawchemy.filter_field()`, with neither `ops` nor `apply`, force-includes a field the decorator's
  `include`/`exclude` would otherwise have left out, with its full default comparison.

`ops` and `apply` are mutually exclusive on the same field.

`ops` values are typed: `strawchemy` exports one operator alias per comparison input — `EqualityOperator`,
`OrderOperator`, `TextOperator`, `ArrayOperator`, `DateOperator`, `TimeOperator`, `DateTimeOperator`,
`TimeDeltaOperator` — plus `ComparisonOperator` for their union, which is what `ops=` accepts. A typo is a type
error, and you can name a vocabulary yourself (`MY_OPS: list[TextOperator] = ["eq", "like"]`). Which operators a
given field actually accepts still depends on its column or aggregation function, and that narrower check happens
when the filter class is built. `ops=` does not apply to JSON or geo columns: their comparisons declare operators
outside the registry these aliases mirror.

On an `ops` or bare field the annotation names either the column's data type (`str` for `name`) or the column's
comparison input (`TextComparison`); anything else — including `Any` — raises `StrawchemyFieldError` at import time.
An `apply` field is different: it has no column, so its annotation *defines* the generated GraphQL input type
(`sweeter_than: int` above) and is used verbatim. A bare `strawchemy.filter_field()` needs no annotation at all.

Any `strawberry.field` keyword argument — `name`, `description`, `deprecation_reason`, `metadata`, `directives` —
passes straight through to the generated field:

```python
class FruitFineGrainedFilter:
    name: TextComparison = strawchemy.filter_field(
        ops=["eq"], name="fruitName", description="Filter by fruit name", deprecation_reason="use `id` instead"
    )
```
