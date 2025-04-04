# Strawchemy

[![🔂 Tests and linting](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/gazorby/strawchemy/graph/badge.svg?token=BCU8SX1MJ7)](https://codecov.io/gh/gazorby/strawchemy) [![PyPI Downloads](https://static.pepy.tech/badge/strawchemy)](https://pepy.tech/projects/strawchemy)

Generates GraphQL types, inputs, queries and resolvers directly from SQLAlchemy models.

## Features

- 🔄 **Automatic Type Generation**: Generate strawberry types from SQLAlchemy models

- 🧠 **Smart Resolvers**: Automatically generates single, optimized database queries for a given GraphQL request

- 🔍 **Comprehensive Filtering**: Rich filtering capabilities on most data types, including PostGIS geo columns

- 📄 **Pagination Support**: Built-in offset-based pagination

- 📊 **Aggregation Queries**: Support for aggregation functions like count, sum, avg, min, max, and statistical functions

- ⚡ **Sync/Async Support**: Works with both synchronous and asynchronous SQLAlchemy sessions

- 🛢 **Database Support**: Currently only PostgreSQL is officially supported and tested (using [asyncpg](https://github.com/MagicStack/asyncpg) or [psycopg3 sync/async](https://www.psycopg.org/psycopg3/))

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Mapping SQLAlchemy Models](#mapping-sqlalchemy-models)
- [Resolver Generation](#resolver-generation)
- [Pagination](#pagination)
- [Filtering](#filtering)
- [Aggregations](#aggregations)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [License](#license)

## Installation

Strawchemy is available on PyPi

```console
pip install strawchemy
```

Strawchemy has the following optional dependencies:

- `geo` : Enable Postgis support through [geoalchemy2](https://github.com/geoalchemy/geoalchemy2)

To install these dependencies along with strawchemy:

```console
pip install strawchemy[geo]
```

## Quick Start

```python
import strawberry
from strawchemy import Strawchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Initialize the strawchemy mapper
strawchemy = Strawchemy()


# Define SQLAlchemy models
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    author: Mapped[User] = relationship("User", back_populates="posts")


# Map models to GraphQL types
@strawchemy.type(User, include="all")
class UserType:
    pass


@strawchemy.type(Post, include="all")
class PostType:
    pass


# Create filter inputs
@strawchemy.filter_input(User, include="all")
class UserFilter:
    pass


@strawchemy.filter_input(Post, include="all")
class PostFilter:
    pass


# Create order by inputs
@strawchemy.order_by_input(User, include="all")
class UserOrderBy:
    pass


@strawchemy.order_by_input(Post, include="all")
class PostOrderBy:
    pass


# Define GraphQL query fields
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by=UserOrderBy, pagination=True)
    posts: list[PostType] = strawchemy.field(filter_input=PostFilter, order_by=PostOrderBy, pagination=True)

# Create schema
schema = strawberry.Schema(query=Query)
```

```graphql
{
  # Users with pagination, filtering, and ordering
  users(
    offset: 0
    limit: 10
    filter: { name: { contains: "John" } }
    orderBy: { name: ASC }
  ) {
    id
    name
    posts {
      id
      title
      content
    }
  }

  # Posts with exact title match
  posts(filter: { title: { eq: "Introduction to GraphQL" } }) {
    id
    title
    content
    author {
      id
      name
    }
  }
}
```

## Mapping SQLAlchemy Models

Strawchemy provides an easy way to map SQLAlchemy models to GraphQL types using the `@strawchemy.type` decorator. You can include/exclude specific fields or have strawchemy map all columns/relationships of the model and it's children.

<details>
<summary>Mapping example</summary>

Include columns and relationships

```python
import strawberry
from strawchemy import Strawchemy

# Assuming these models are defined as in the Quick Start example
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

strawchemy = Strawchemy()


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


@strawchemy.type(User, include="all")
class UserType:
    pass
```

Including/excluding specific fields

```python
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    password: Mapped[str]


# Include specific fields
@strawchemy.type(User, include=["id", "name"])
class UserType:
    pass


# Exclude specific fields
@strawchemy.type(User, exclude=["password"])
class UserType:
    pass


# Include all fields
@strawchemy.type(User, include="all")
class UserType:
    pass
```

Add a custom fields

```python
from strawchemy import ModelInstance

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]


@strawchemy.type(User, include="all")
class UserType:
    instance: ModelInstance[User]

    @strawchemy.field
    def full_name(self) -> str:
        return f"{self.instance.first_name} {self.instance.last_name}"
```

See the [custom resolvers](#custom-resolvers) for more details

</details>

### Type override

By default, strawchemy generates strawberry types when visiting the model and the following relationships, but only if you have not already defined a type with the same name using the @strawchemy.type decorator, otherwise you will see an error.

To explicitly tell strawchemy to use your type, you need to define it with `@strawchemy.type(override=True)`.

<details>
<summary>Using the Override Parameter</summary>

```python
from strawchemy import Strawchemy

strawchemy = Strawchemy()

# Define models
class Color(Base):
    __tablename__ = "color"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    fruits: Mapped[list["Fruit"]] = relationship("Fruit", back_populates="color")

class Fruit(Base):
    __tablename__ = "fruit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    color_id: Mapped[int] = mapped_column(ForeignKey("color.id"))
    color: Mapped[Color] = relationship("Color", back_populates="fruits")

# Define a type with override=True
@strawchemy.type(Color, include="all", override=True)
class ColorType:
    fruits: auto
    name: int

# Define another type that uses the same model
@strawchemy.type(Fruit, include="all", override=True)
class FruitType:
    name: int
    color: auto  # This will use the ColorType defined above

# Define a query that uses these types
@strawberry.type
class Query:
    fruit: FruitType = strawchemy.field()
```

The `override` parameter is useful in the following scenarios:

1. **Type Reuse**: When you need to use the same type in multiple places where the same model is referenced.
2. **Auto-generated Type Override**: When you want to override the default auto-generated type for a model.
3. **Custom Type Names**: When you want to use a custom name for your type but still have it recognized as the type for a specific model.

Without setting `override=True`, you would get an error like:

```
Type `FruitType` cannot be auto generated because it's already declared.
You may want to set `override=True` on the existing type to use it everywhere.
```

This happens when Strawchemy tries to auto-generate a type for a model that already has a type defined for it.

You can also use `override=True` with input types:

```python
@strawchemy.order_by_input(Fruit, include="all", override=True)
class FruitOrderBy:
    # Custom order by fields
    override: bool = True
```

</details>
</details>

## Resolver Generation

Strawchemy automatically generates resolvers for your GraphQL fields. You can use the `strawchemy.field()` function to generate fields that query your database

<details>
<summary>Resolvers example</summary>

```python
@strawberry.type
class Query:
    # Simple field that returns a list of users
    users: list[UserType] = strawchemy.field()
    # Field with filtering, ordering, and pagination
    filtered_users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by=UserOrderBy, pagination=True)
    # Field that returns a single user by ID
    user: UserType = strawchemy.field()
```

</details>

While Strawchemy automatically generates resolvers for most use cases, you can also create custom resolvers for more complex scenarios. There are two main approaches to creating custom resolvers:

### Using Repository Directly

When using `strawchemy.field()` as a function, strawchemy creates a resolver that delegates data fetching to the `StrawchemySyncRepository` or `StrawchemyAsyncRepository` classes depending on the SQLAlchemy session type.
You can create custom resolvers by using the `@strawchemy.field` as a decorator and working directly with the repository:

<details>
<summary>Custom resolvers using repository</summary>

```python
from sqlalchemy import select, true
from strawchemy import StrawchemySyncRepository

@strawberry.type
class Query:
    @strawchemy.field
    def red_color(self, info: strawberry.Info) -> ColorType:
        # Create a repository with a predefined filter
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
        # Return a single result (will raise an exception if not found)
        return repo.get_one()

    @strawchemy.field
    def get_color_by_name(self, info: strawberry.Info, color: str) -> ColorType | None:
        # Create a repository with a custom filter statement
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        # Return a single result or None if not found
        return repo.get_one_or_none()

    @strawchemy.field
    def get_color_by_id(self, info: strawberry.Info, id: str) -> ColorType | None:
        repo = StrawchemySyncRepository(ColorType, info)
        # Return a single result or None if not found
        return repo.get_by_id(id=id)

    @strawchemy.field
    def public_colors(self, info: strawberry.Info) -> ColorType:
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.public.is_(true())))
        # Return a list of results
        return repo.list()
```

For async resolvers, use `StrawchemyAsyncRepository` which is the async variant of `StrawchemySyncRepository`:

```python
from strawchemy import StrawchemyAsyncRepository

@strawberry.type
class Query:
    @strawchemy.field
    async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        return await repo.get_one_or_none()
```

The repository provides several methods for fetching data:

- `get_one()`: Returns a single result, raises an exception if not found
- `get_one_or_none()`: Returns a single result or None if not found
- `get_by_id()`: Returns a single result filtered on primary key
- `list()`: Returns a list of results

</details>

### Query Hooks

Strawchemy provides query hooks that allow you to customize query behavior. Query hooks give you fine-grained control over how SQL queries are constructed and executed.

<details>
<summary>Using query hooks</summary>

The `QueryHook` base class provides several methods that you can override to customize query behavior:

#### Modifying the statement

You can subclass `QueryHook` and override the `apply_hook` method apply changes to the statement. By default, it returns it unchanged. This method is only for filtering or ordering customizations, if you want to explicitly load columns or relationships, use the `load` parameter instead.

```python
from strawchemy import ModelInstance, QueryHook
from sqlalchemy import Select, select
from sqlalchemy.orm.util import AliasedClass

# Define a model and type
class Fruit(Base):
    __tablename__ = "fruit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    adjectives: Mapped[list[str]] = mapped_column(ARRAY(String))

# Apply the hook at the field level
@strawchemy.type(Fruit, exclude={"color"})
class FruitTypeWithDescription:
    instance: ModelInstance[Fruit]

    # Use QueryHook to ensure specific columns are loaded
    @strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return f"The {self.instance.name} is {', '.join(self.instance.adjectives)}"

# Create a custom query hook for filtering
class FilterFruitHook(QueryHook[Fruit]):
    def apply_hook(self, statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit]) -> Select[tuple[Fruit]]:
        # Add a custom WHERE clause
        return statement.where(alias.name == "Apple")

# Apply the hook at the type level
@strawchemy.type(Fruit, exclude={"color"}, query_hook=FilterFruitHook())
class FilteredFruitType:
    pass
```

Important notes when implementing `apply_hooks`:

- You must use the provided `alias` parameter to refer to columns of the model on which the hook is applied. Otherwise, the statement may fail.
- The GraphQL context is available through `self.info` within hook methods.
- You must set a `ModelInstance` typed attribute if you want to access the model instance values.
  The `instance` attribute is matched by the `ModelInstance[Fruit]` type hint, so you can give it any name you want.

#### Load specific columns/relationships

The `load` parameter specify columns and relationships that should always be loaded, even if not directly requested in the GraphQL query. This is useful for:

- Ensuring data needed for computed properties is available
- Loading columns or relationships required for custom resolvers

Examples of using the `load` parameter:

```python
# Load specific columns
@strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.adjectives]))
def description(self) -> str:
    return f"The {self.instance.name} is {', '.join(self.instance.adjectives)}"

# Load a relationship without specifying columns
@strawchemy.field(query_hook=QueryHook(load=[Fruit.farms]))
def pretty_farms(self) -> str:
    return f"Farms are: {', '.join(farm.name for farm in self.instance.farms)}"

# Load a relationship with specific columns
@strawchemy.field(query_hook=QueryHook(load=[(Fruit.color, [Color.name, Color.created_at])]))
def pretty_color(self) -> str:
    return f"Color is {self.instance.color.name}" if self.instance.color else "No color!"

# Load nested relationships
@strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [(Fruit.farms, [FruitFarm.name])])]))
def farms(self) -> str:
    return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"
```

</details>

## Pagination

Strawchemy supports offset-based pagination out of the box.

<details>
<summary>Pagination example:</summary>

Enable pagination on fields:

```python
from strawchemy.types import DefaultOffsetPagination

@strawberry.type
class Query:
    # Enable pagination with default settings
    users: list[UserType] = strawchemy.field(pagination=True)
    # Customize pagination defaults
    users_custom_pagination: list[UserType] = strawchemy.field(pagination=DefaultOffsetPagination(limit=20))
```

In your GraphQL queries, you can use the `offset` and `limit` parameters:

```graphql
{
  users(offset: 0, limit: 10) {
    id
    name
  }
}
```

You can also enable pagination for nested relationships:

```python
@strawchemy.type(User, include="all", child_pagination=True)
class UserType:
    pass
```

Then in your GraphQL queries:

```graphql
{
  users {
    id
    name
    posts(offset: 0, limit: 5) {
      id
      title
    }
  }
}
```

</details>

## Filtering

Strawchemy provides powerful filtering capabilities.

<details>
<summary>Filtering example</summary>

First, create a filter input type:

```python
@strawchemy.filter_input(User, include="all")
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
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
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

### Geo Filters

Strawchemy supports spatial filtering capabilities for geometry fields using [GeoJSON](https://datatracker.ietf.org/doc/html/rfc7946). To use geo filters, you need to have PostGIS installed and enabled in your PostgreSQL database.

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

@strawchemy.filter_input(GeoModel, include="all")
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

## Aggregations

Strawchemy automatically exposes aggregation fields for list relationships.

When you define a model with a list relationship, the corresponding GraphQL type will include an aggregation field for that relationship, named `<field_name>Aggregate`.

<details>
<summary> Basic aggregation example:</summary>

With the folliing model definitions:

```python
class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    author: Mapped[User] = relationship("User", back_populates="posts")
```

And the corresponding GraphQL types:

```python
@strawchemy.type(User, include="all")
class UserType:
    pass


@strawchemy.type(Post, include="all")
class PostType:
    pass
```

You can query aggregations on the `posts` relationship:

```graphql
{
  users {
    id
    name
    postsAggregate {
      count
      min {
        title
      }
      max {
        title
      }
      # Other aggregation functions are also available
    }
  }
}
```

</details>

### Filtering by relationship aggregations

You can also filter entities based on aggregations of their related entities.

<details>
<summary>Aggregation filtering example</summary>

Define types with filters:

```python
@strawchemy.filter_input(User, include="all")
class UserFilter:
    pass


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

For example, to find users who have more than 5 posts:

```graphql
{
  users(
    filter: {
      postsAggregate: { count: { arguments: [id], predicate: { gt: 5 } } }
    }
  ) {
    id
    name
    postsAggregate {
      count
    }
  }
}
```

You can use various predicates for filtering:

```graphql
# Users with exactly 3 posts
users(filter: {
  postsAggregate: {
    count: {
      arguments: [id]
      predicate: { eq: 3 }
    }
  }
})

# Users with posts containing "GraphQL" in the title
users(filter: {
  postsAggregate: {
    maxString: {
      arguments: [title]
      predicate: { contains: "GraphQL" }
    }
  }
})

# Users with an average post length greater than 1000 characters
users(filter: {
  postsAggregate: {
    avg: {
      arguments: [contentLength]
      predicate: { gt: 1000 }
    }
  }
})
```

</details>

#### Distinct aggregations

<details>
<summary>Distinct aggregation filtering example</summary>

You can also use the `distinct` parameter to count only distinct values:

```graphql
{
  users(
    filter: {
      postsAggregate: {
        count: { arguments: [category], predicate: { gt: 2 }, distinct: true }
      }
    }
  ) {
    id
    name
  }
}
```

This would find users who have posts in more than 2 distinct categories.

</details>

### Root aggregations

Strawchemy supports query level aggregations.

<details>
<summary>Root aggregations example:</summary>

First, create an aggregation type:

```python
@strawchemy.aggregation_type(User, include="all")
class UserAggregationType:
    pass
```

Then set up the root aggregations on the field:

```python
@strawberry.type
class Query:
    users_aggregations: UserAggregationType = strawchemy.field(root_aggregations=True)
```

Now you can use aggregation functions on the result of your query:

```graphql
{
  usersAggregations {
    aggregations {
      # Basic aggregations
      count

      sum {
        age
      }

      avg {
        age
      }

      min {
        age
        createdAt
      }
      max {
        age
        createdAt
      }

      # Statistical aggregations
      stddev {
        age
      }
      variance {
        age
      }
    }
    # Access the actual data
    nodes {
      id
      name
      age
    }
  }
}
```

</details>

## Configuration

Strawchemy can be configured when initializing the mapper.

### Configuration Options

| Option                     | Type                                                        | Default                  | Description                                                                                                                                                           |
| -------------------------- | ----------------------------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `session_getter`           | `Callable[[Info], Session]`                                 | `default_session_getter` | Function to retrieve SQLAlchemy session from strawberry `Info` object. By default, it retrieves the session from `info.context.session`.                              |
| `auto_snake_case`          | `bool`                                                      | `True`                   | Automatically convert snake cased names to camel case in GraphQL schema.                                                                                              |
| `repository_type`          | `type[Repository] \| "auto"`                                | `"auto"`                 | Repository class to use for auto resolvers. When set to `"auto"`, Strawchemy will automatically choose between sync and async repositories based on the session type. |
| `filter_overrides`         | `OrderedDict[tuple[type, ...], type[SQLAlchemyFilterBase]]` | `None`                   | Override default filters with custom filters. This allows you to provide custom filter implementations for specific column types.                                     |
| `execution_options`        | `dict[str, Any]`                                            | `None`                   | SQLAlchemy execution options for repository operations. These options are passed to the SQLAlchemy `execution_options()` method.                                      |
| `pagination_default_limit` | `int`                                                       | `100`                    | Default pagination limit when `pagination=True`.                                                                                                                      |
| `pagination`               | `bool`                                                      | `False`                  | Enable/disable pagination on list resolvers by default.                                                                                                               |
| `default_id_field_name`    | `str`                                                       | `"id"`                   | Name for primary key fields arguments on primary key resolvers.                                                                                                       |
| `dialect`                  | `Literal["postgresql"]`                                     | `"postgresql"`           | Database dialect to use. Currently, only PostgreSQL is supported.                                                                                                     |

### Example

```python
from strawchemy import Strawchemy

# Custom session getter function
def get_session_from_context(info):
    return info.context.db_session

# Initialize with custom configuration
strawchemy = Strawchemy(
    session_getter=get_session_from_context,
    auto_snake_case=True,
    pagination=True,
    pagination_default_limit=50,
    default_id_field_name="pk",
)
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

## License

This project is licensed under the terms of the license included in the [LICENCE](LICENCE) file.
