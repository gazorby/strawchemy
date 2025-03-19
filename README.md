# Strawchemy

Strawchemy is a powerful library that seamlessly integrates [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) with [Strawberry GraphQL](https://github.com/strawberry-graphql/strawberry) to quickly build efficient GraphQL APIs with minimal boilerplate code. It automatically generates GraphQL types, resolvers, filters, and more from your SQLAlchemy models.

## Features

- 🔄 **Automatic Type Generation**: Generate strawberry types from SQLAlchemy models

- 🧠 **Smart Resolvers**: Automatically generates single, optimized database queries for a given GraphQL request

- 🔍 **Comprehensive Filtering**: Rich filtering capabilities on most data types, including PostGIS geo columns

- 📄 **Pagination Support**: Built-in offset-based pagination

- 📊 **Aggregation Queries**: Support for aggregation functions like count, sum, avg, min, max, and statistical functions

- ⚡ **Sync/Async Support**: Works with both synchronous and asynchronous SQLAlchemy sessions

- 🛢 **Database Support**: Currently only PostgreSQL is officially supported and tested

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

Here's a simple example of how to use **Strawchemy**:

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

Example GraphQL query:

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

Strawchemy provides a simple way to map SQLAlchemy models to GraphQL types using the `@strawchemy.type` decorator:

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

You can customize which fields to include or exclude:

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

You can also add custom fields to your GraphQL type:

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

## Resolver Generation

Strawchemy automatically generates resolvers for your GraphQL fields. You can use the `strawchemy.field` function to create fields that query your database:

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

For async resolvers, use `StrawchemyAsyncRepository`:

```python
from strawchemy import StrawchemyAsyncRepository

@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)
```

### Custom Resolvers

While Strawchemy automatically generates resolvers for most use cases, you can also create custom resolvers for more complex scenarios. There are two main approaches to creating custom resolvers:

#### 1. Using Repository Directly

You can create custom resolvers by using the `@strawchemy.field` decorator and directly working with the repository:

```python
from sqlalchemy import select
from strawchemy import StrawchemySyncRepository # Use StrawchemyAsyncRepository in async context

@strawberry.type
class Query:
    @strawchemy.field
    def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        # Create a repository with a custom filter statement
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        # Return a single result or None if not found
        return repo.get_one_or_none()

    @strawchemy.field
    def red_color(self, info: strawberry.Info) -> ColorType:
        # Create a repository with a predefined filter
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
        # Return a single result (will raise an exception if not found)
        return repo.get_one()
```

For async resolvers, use `StrawchemyAsyncRepository` and `await` the repository methods:

```python
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
- `get_many()`: Returns a list of results

#### 2. Using Query Hooks

Strawchemy provides query hooks that allow you to customize query behavior. These hooks can be applied at both the field level and the type level:

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

You must set a `ModelInstance` typed attribute if you want to access the model instance values.
The `instance` attribute is matched by the `ModelInstance[Fruit]` type hint, so you can give it any name you want.

Query hooks provide powerful ways to:

- Ensure specific columns are always loaded, even if not directly requested in the GraphQL query. (useful to expose hybrid properties in the schema)
- Apply custom filters based on context (e.g., user role)
- Modify the underlying SQLAlchemy query for optimization or security

## Pagination

Strawchemy supports offset-based pagination out of the box:

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

## Filtering

Strawchemy provides powerful filtering capabilities. First, create a filter input type:

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
}
```

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

Strawchemy supports the following geo filter operations:

- **containsGeometry**: Filters for geometries that contain the specified GeoJSON geometry
- **withinGeometry**: Filters for geometries that are within the specified GeoJSON geometry
- **isNull**: Filters for null or non-null geometry values

These filters work with all geometry types supported by PostGIS, including:

- Point
- LineString
- Polygon
- MultiPoint
- MultiLineString
- MultiPolygon
- Geometry (generic geometry type)

## Aggregations

Strawchemy automatically exposes aggregation fields for list relationships. When you define a model with a list relationship, the corresponding GraphQL type will include an aggregation field for that relationship.

For example, with the following models:

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

### Filtering by relationship aggregations

You can also filter entities based on aggregations of their related entities. For example, to find users who have more than 5 posts:

```python
@strawchemy.filter_input(User, include="all")
class UserFilter:
    pass


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

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

#### Distinct aggregations

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

### Root aggregations

Strawchemy supports query level aggregations. First, create an aggregation type:

```python
@strawchemy.aggregation_type(User, include="all")
class UserAggregationType:
    pass
```

Then use it in your field with the `root_aggregations` parameter:

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

## Configuration

Strawchemy can be configured when initializing the mapper. Here's a complete reference of all available configuration options:

```python
from strawchemy import Strawchemy

# Initialize with default configuration
strawchemy = Strawchemy()

# Or customize the configuration
strawchemy = Strawchemy(auto_snake_case=True, pagination=True)
```

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
