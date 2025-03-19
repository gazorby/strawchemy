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
<summary>SQLAlchemy models</summary>

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

</details>

<details>
<summary>Customizing Fields</summary>

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

</details>

<details>
<summary>Adding Custom Fields</summary>

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

</details>

## Resolver Generation

Strawchemy automatically generates resolvers for your GraphQL fields.

<details>
<summary>You can use the `strawchemy.field()` function to generate fields that query your database:</summary>

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

### Custom Resolvers

While Strawchemy automatically generates resolvers for most use cases, you can also create custom resolvers for more complex scenarios. There are two main approaches to creating custom resolvers:

#### 1. Using Repository Directly

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

</details>

For async resolvers, use `StrawchemyAsyncRepository` which is the async variant of `StrawchemySyncRepository`:

<details>
<summary>Async repository</summary>

```python
from strawchemy import StrawchemyAsyncRepository

@strawberry.type
class Query:
    @strawchemy.field
    async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        return await repo.get_one_or_none()
```

</details>

The repository provides several methods for fetching data:

- `get_one()`: Returns a single result, raises an exception if not found
- `get_one_or_none()`: Returns a single result or None if not found
- `get_by_id()`: Returns a single result filtered on primary key
- `list()`: Returns a list of results

#### 2. Using Query Hooks

Strawchemy provides query hooks that allow you to customize query behavior. These hooks can be applied at both the field level and the type level:

<details>
<summary>Using query hooks</summary>

```python
from strawchemy import ModelInstance, QueryHook
from strawchemy.sqlalchemy.hook import QueryHookResult
from sqlalchemy import Select
from sqlalchemy.orm.util import AliasedClass
from strawberry import Info

@strawchemy.type(Fruit, exclude={"color"})
class FruitTypeWithDescription:
    instance: ModelInstance[Fruit]

    # Use QueryHook with always_load parameter to ensure columns are loaded
    @strawchemy.field(query_hook=QueryHook(always_load=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return f"The {self.instance.name} is {', '.join(self.instance.adjectives)}"

# Custom query hook function
def user_fruit_filter(
    statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit], info: Info
) -> QueryHookResult[Fruit]:
    # Add a custom filter based on context
    if info.context.role == "user":
        return QueryHookResult(statement=statement.where(alias.name == "Apple"))
    return QueryHookResult(statement=statement)

# Type-level query hook
@strawchemy.type(Fruit, exclude={"color"}, query_hook=user_fruit_filter)
class FilteredFruitType:
    pass
```

</details>

> [!Note]\
> You must set a `ModelInstance` typed attribute if you want to access the model instance values.
> The `instance` attribute is matched by the `ModelInstance[Fruit]` type hint, so you can give it any name you want.

Query hooks provide powerful ways to:

- Ensure specific columns are always loaded, even if not directly requested in the GraphQL query. (useful to expose hybrid properties in the schema)
- Apply custom filters based on context (e.g., user role)
- Modify the underlying SQLAlchemy query for optimization or security

## Pagination

Strawchemy supports offset-based pagination out of the box.

<details>
<summary>Enable pagination on fields:</summary>

```python
from strawchemy.types import DefaultOffsetPagination

@strawberry.type
class Query:
    # Enable pagination with default settings
    users: list[UserType] = strawchemy.field(pagination=True)
    # Customize pagination defaults
    users_custom_pagination: list[UserType] = strawchemy.field(pagination=DefaultOffsetPagination(limit=20))
```

</details>

<details>
<summary>In your GraphQL queries, you can use the `offset` and `limit` parameters:</summary>

```graphql
{
  users(offset: 0, limit: 10) {
    id
    name
  }
}
```

</details>

<details>
<summary>You can also enable pagination for nested relationships:</summary>

```python
@strawchemy.type(User, include="all", child_pagination=True)
class UserType:
    pass
```

</details>

<details>
<summary>Then in your GraphQL queries:</summary>

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
<summary>First, create a filter input type:</summary>

```python
@strawchemy.filter_input(User, include="all")
class UserFilter:
    pass
```

</details>

<details>
<summary>Then use it in your field:</summary>

```python
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

</details>

<details>
<summary>Now you can use various filter operations in your GraphQL queries:</summary>

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
}
```

</details>

Strawchemy supports a wide range of filter operations:

- **Common to most types**: `eq`, `neq`, `isNull`, `in_`, `nin_`
- **Numeric types (Int, Float, Decimal)**: `gt`, `gte`, `lt`, `lte`
- **String**: `like`, `nlike`, `ilike`, `nilike`, `regexp`, `nregexp`, `startswith`, `endswith`, `contains`, `istartswith`, `iendswith`, `icontains`
- **JSON**: `contains`, `containedIn`, `hasKey`, `hasKeyAll`, `hasKeyAny`
- **Array**: `contains`, `containedIn`, `overlap`
- **Date**: `year`, `month`, `day`, `weekDay`, `week`, `quarter`, `isoYear`, `isoWeekDay`
- **DateTime**: All Date filters plus `hour`, `minute`, `second`
- **Time**: `hour`, `minute`, `second`
- **Logical**: `_and`, `_or`, `_not`

### Geo Filters

Strawchemy supports spatial filtering capabilities for geometry fields using [GeoJSON](https://datatracker.ietf.org/doc/html/rfc7946). To use geo filters, you need to have PostGIS installed and enabled in your PostgreSQL database.

<details>
<summary>Define models and types</summary>

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

</details>

<details>
<summary>Then you can use the following geo filter operations in your GraphQL queries:</summary>

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
<summary> For example, with the following models:</summary>

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

</details>
<details>
<summary> And the corresponding GraphQL types:</summary>

```python
@strawchemy.type(User, include="all")
class UserType:
    pass


@strawchemy.type(Post, include="all")
class PostType:
    pass
```

</details>
<details>
<summary> You can query aggregations on the `posts` relationship:</summary>

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
<summary>Define types with filters</summary>

```python
@strawchemy.filter_input(User, include="all")
class UserFilter:
    pass


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

</details>

<details>
<summary>For example, to find users who have more than 5 posts::</summary>

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

</details>

<details>
<summary>You can use various predicates for filtering:</summary>

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
<summary>You can also use the `distinct` parameter to count only distinct values:</summary>

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

</details>

This would find users who have posts in more than 2 distinct categories.

### Root aggregations

Strawchemy supports query level aggregations.

<details>
<summary>First, create an aggregation type:</summary>

```python
@strawchemy.aggregation_type(User, include="all")
class UserAggregationType:
    pass
```

</details>

<details>
<summary>Then set up the root aggregations on the field:</summary>

```python
@strawberry.type
class Query:
    users_aggregations: UserAggregationType = strawchemy.field(root_aggregations=True)
```

</details>

<details>
<summary>Now you can use aggregation functions on the result of your query:</summary>

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
