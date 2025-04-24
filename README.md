# Strawchemy

[![🔂 Tests and linting](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/gazorby/strawchemy/graph/badge.svg?token=BCU8SX1MJ7)](https://codecov.io/gh/gazorby/strawchemy) [![PyPI Downloads](https://static.pepy.tech/badge/strawchemy)](https://pepy.tech/projects/strawchemy)

Generates GraphQL types, inputs, queries and resolvers directly from SQLAlchemy models.

## Features

- 🔄 **Type Generation**: Generate strawberry types from SQLAlchemy models

- 🧠 **Smart Resolvers**: Automatically generates single, optimized database queries for a given GraphQL request

- 🔍 **Filtering**: Rich filtering capabilities on most data types, including PostGIS geo columns

- 📄 **Pagination**: Built-in offset-based pagination

- 📊 **Aggregation**: Support for aggregation functions like count, sum, avg, min, max, and statistical functions

- 🔀 **CRUD**: Full support for Create, Read, Update, and Delete mutations with relationship handling

- 🪝 **Hooks**: Customize query behavior with query hooks: add filtering, load extra column etc.

- ⚡ **Sync/Async**: Works with both sync and async SQLAlchemy sessions

- 🛢 **Database**: Currently, only PostgreSQL is officially supported and tested (using [asyncpg](https://github.com/MagicStack/asyncpg) or [psycopg3 sync/async](https://www.psycopg.org/psycopg3/))

> [!Warning]
>
> Please note that strawchemy is currently in a pre-release stage of development. This means that the library is still under active development and the initial API is subject to change. We encourage you to experiment with strawchemy and provide feedback, but be sure to pin and update carefully until a stable release is available.

## Database support

Currently, only PostgreSQL is officially supported and tested (using [asyncpg](https://github.com/MagicStack/asyncpg) or [psycopg3 sync/async](https://www.psycopg.org/psycopg3/))

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Mapping SQLAlchemy Models](#mapping-sqlalchemy-models)
- [Resolver Generation](#resolver-generation)
- [Pagination](#pagination)
- [Filtering](#filtering)
- [Aggregations](#aggregations)
- [Mutations](#mutations)
- [Async Support](#async-support)
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
@strawchemy.filter(User, include="all")
class UserFilter:
    pass


@strawchemy.filter(Post, include="all")
class PostFilter:
    pass


# Create order by inputs
@strawchemy.order(User, include="all")
class UserOrderBy:
    pass


@strawchemy.order(Post, include="all")
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
@strawchemy.order(Fruit, include="all", override=True)
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
@strawchemy.filter(User, include="all")
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
@strawchemy.aggregate(User, include="all")
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

## Mutations

Strawchemy provides a powerful way to create GraphQL mutations for your SQLAlchemy models. These mutations allow you to create, update, and delete data through your GraphQL API.

<details>
<summary>Mutations example</summary>

```python
import strawberry
from strawchemy import Strawchemy, StrawchemySyncRepository, StrawchemyAsyncRepository

# Initialize the strawchemy mapper
strawchemy = Strawchemy()

# Define input types for mutations
@strawchemy.input(User, include=["name", "email"])
class UserCreateInput:
    pass

@strawchemy.input(User, include=["id", "name", "email"])
class UserUpdateInput:
    pass

@strawchemy.filter(User, include="all")
class UserFilter:
    pass

# Define GraphQL mutation fields
@strawberry.type
class Mutation:
    # Create mutations
    create_user: UserType = strawchemy.create(UserCreateInput)
    create_users: list[UserType] = strawchemy.create(UserCreateInput)  # Batch creation

    # Update mutations
    update_user: UserType = strawchemy.update_by_ids(UserUpdateInput)
    update_users: list[UserType] = strawchemy.update_by_ids(UserUpdateInput)  # Batch update
    update_users_filter: list[UserType] = strawchemy.update(UserUpdateInput, UserFilter)  # Update with filter

    # Delete mutations
    delete_users: list[UserType] = strawchemy.delete()  # Delete all
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)  # Delete with filter

# Create schema with mutations
schema = strawberry.Schema(query=Query, mutation=Mutation)
```

</details>

### Create Mutations

Create mutations allow you to insert new records into your database. Strawchemy provides two types of create mutations:

1. **Single entity creation**: Creates a single record
2. **Batch creation**: Creates multiple records in a single operation

<details>
<summary>Create mutation examples</summary>

#### Basic Create Mutation

```python
# Define input type for creation
@strawchemy.input(Color, include=["name"])
class ColorCreateInput:
    pass

@strawberry.type
class Mutation:
    # Single entity creation
    create_color: ColorType = strawchemy.create(ColorCreateInput)

    # Batch creation
    create_colors: list[ColorType] = strawchemy.create(ColorCreateInput)
```

GraphQL usage:

```graphql
# Create a single color
mutation {
  createColor(data: { name: "Purple" }) {
    id
    name
  }
}

# Create multiple colors in one operation
mutation {
  createColors(data: [{ name: "Teal" }, { name: "Magenta" }]) {
    id
    name
  }
}
```

</details>

### Working with Relationships in Create Mutations

Strawchemy supports creating entities with relationships. You can:

1. **Set existing relationships**: Link to existing records
2. **Create nested relationships**: Create related records in the same mutation
3. **Set to null**: Remove relationships

<details>
<summary>Create with relationships examples</summary>

#### To-One Relationships

```python
@strawchemy.input(Fruit, include=["name", "adjectives"])
class FruitCreateInput:
    # Define relationship inputs
    color: auto  # 'auto' will generate appropriate relationship inputs
```

GraphQL usage:

```graphql
# Set an existing relationship
mutation {
  createFruit(
    data: {
      name: "Apple"
      adjectives: ["sweet", "crunchy"]
      color: { set: { id: "123e4567-e89b-12d3-a456-426614174000" } }
    }
  ) {
    id
    name
    color {
      id
      name
    }
  }
}

# Create a new related entity
mutation {
  createFruit(
    data: {
      name: "Banana"
      adjectives: ["yellow", "soft"]
      color: { create: { name: "Yellow" } }
    }
  ) {
    id
    name
    color {
      id
      name
    }
  }
}

# Set relationship to null
mutation {
  createFruit(
    data: {
      name: "Strawberry"
      adjectives: ["red", "sweet"]
      color: { set: null }
    }
  ) {
    id
    name
    color {
      id
    }
  }
}
```

#### To-Many Relationships

```python
@strawchemy.input(Color, include=["name"])
class ColorCreateInput:
    # Define to-many relationship inputs
    fruits: auto  # 'auto' will generate appropriate relationship inputs
```

GraphQL usage:

```graphql
# Set existing to-many relationships
mutation {
  createColor(
    data: {
      name: "Red"
      fruits: { set: [{ id: "123e4567-e89b-12d3-a456-426614174000" }] }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}

# Add to existing to-many relationships
mutation {
  createColor(
    data: {
      name: "Green"
      fruits: { add: [{ id: "123e4567-e89b-12d3-a456-426614174000" }] }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}

# Create new related entities
mutation {
  createColor(
    data: {
      name: "Blue"
      fruits: {
        create: [
          { name: "Blueberry", adjectives: ["small", "blue"] }
          { name: "Plum", adjectives: ["juicy", "purple"] }
        ]
      }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}
```

#### Nested Relationships

You can create deeply nested relationships:

```graphql
mutation {
  createColor(
    data: {
      name: "White"
      fruits: {
        create: [
          {
            name: "Grape"
            adjectives: ["tangy", "juicy"]
            farms: { create: [{ name: "Bio farm" }] }
          }
        ]
      }
    }
  ) {
    name
    fruits {
      name
      farms {
        name
      }
    }
  }
}
```

</details>

### Update Mutations

Update mutations allow you to modify existing records. Strawchemy provides several types of update mutations:

1. **Update by primary key**: Update a specific record by its ID
2. **Batch update by primary keys**: Update multiple records by their IDs
3. **Update with filter**: Update records that match a filter condition

<details>
<summary>Update mutation examples</summary>

#### Basic Update Mutation

```python
# Define input type for updates
@strawchemy.input(Color, include=["id", "name"])
class ColorUpdateInput:
    pass

@strawchemy.filter(Color, include="all")
class ColorFilter:
    pass

@strawberry.type
class Mutation:
    # Update by ID
    update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)

    # Batch update by IDs
    update_colors: list[ColorType] = strawchemy.update_by_ids(ColorUpdateInput)

    # Update with filter
    update_colors_filter: list[ColorType] = strawchemy.update(
        ColorUpdateInput, ColorFilter
    )
```

GraphQL usage:

```graphql
# Update by ID
mutation {
  updateColor(
    data: { id: "123e4567-e89b-12d3-a456-426614174000", name: "Crimson" }
  ) {
    id
    name
  }
}

# Batch update by IDs
mutation {
  updateColors(
    data: [
      { id: "123e4567-e89b-12d3-a456-426614174000", name: "Crimson" }
      { id: "223e4567-e89b-12d3-a456-426614174000", name: "Navy" }
    ]
  ) {
    id
    name
  }
}

# Update with filter
mutation {
  updateColorsFilter(
    data: { name: "Bright Red" }
    filter: { name: { eq: "Red" } }
  ) {
    id
    name
  }
}
```

</details>

### Working with Relationships in Update Mutations

Similar to create mutations, update mutations support modifying relationships:

<details>
<summary>Update with relationships examples</summary>

#### To-One Relationships

```python
@strawchemy.input(Fruit, include=["id", "name"])
class FruitUpdateInput:
    # Define relationship inputs
    color: auto
```

GraphQL usage:

```graphql
# Set an existing relationship
mutation {
  updateFruit(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red Apple"
      color: { set: { id: "223e4567-e89b-12d3-a456-426614174000" } }
    }
  ) {
    id
    name
    color {
      id
      name
    }
  }
}

# Create a new related entity
mutation {
  updateFruit(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Green Apple"
      color: { create: { name: "Green" } }
    }
  ) {
    id
    name
    color {
      id
      name
    }
  }
}

# Set relationship to null
mutation {
  updateFruit(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Plain Apple"
      color: { set: null }
    }
  ) {
    id
    name
    color {
      id
    }
  }
}
```

#### To-Many Relationships

```python
@strawchemy.input(Color, include=["id", "name"])
class ColorUpdateInput:
    # Define to-many relationship inputs
    fruits: auto
```

GraphQL usage:

```graphql
# Set (replace) to-many relationships
mutation {
  updateColor(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red"
      fruits: { set: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}

# Add to existing to-many relationships
mutation {
  updateColor(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red"
      fruits: { add: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}

# Remove from to-many relationships
mutation {
  updateColor(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red"
      fruits: { remove: [{ id: "223e4567-e89b-12d3-a456-426614174000" }] }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}

# Create new related entities
mutation {
  updateColor(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red"
      fruits: {
        create: [
          { name: "Cherry", adjectives: ["small", "red"] }
          { name: "Strawberry", adjectives: ["sweet", "red"] }
        ]
      }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}
```

#### Combining Operations

You can combine `add` and `create` operations in a single update:

```graphql
mutation {
  updateColor(
    data: {
      id: "123e4567-e89b-12d3-a456-426614174000"
      name: "Red"
      fruits: {
        add: [{ id: "223e4567-e89b-12d3-a456-426614174000" }]
        create: [{ name: "Raspberry", adjectives: ["tart", "red"] }]
      }
    }
  ) {
    id
    name
    fruits {
      id
      name
    }
  }
}
```

Note: You cannot use `set` with `add`, `remove`, or `create` in the same operation for to-many relationships.

</details>

### Delete Mutations

Delete mutations allow you to remove records from your database. Strawchemy provides two types of delete mutations:

1. **Delete all**: Removes all records of a specific type
2. **Delete with filter**: Removes records that match a filter condition

<details>
<summary>Delete mutation examples</summary>

```python
@strawchemy.filter(User, include="all")
class UserFilter:
    pass

@strawberry.type
class Mutation:
    # Delete all users
    delete_users: list[UserType] = strawchemy.delete()

    # Delete users that match a filter
    delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)
```

GraphQL usage:

```graphql
# Delete all users
mutation {
  deleteUsers {
    id
    name
  }
}

# Delete users that match a filter
mutation {
  deleteUsersFilter(filter: { name: { eq: "Alice" } }) {
    id
    name
  }
}
```

The returned data contains the records that were deleted.

</details>

### Input Validation

Strawchemy supports input validation using Pydantic models. You can define validation schemas and apply them to mutations to ensure data meets specific requirements before being processed.

Create Pydantic models for the input type where you want the validation, and set the `validation` parameter on `strawchemy.field`:

<details>
<summary>Validation example</summary>

```python
from models import User, Group
from typing import Annotated
from pydantic import AfterValidator
from strawchemy import InputValidationError, ValidationErrorType

def _check_lower_case(value: str) -> str:
    if not value.islower():
        raise ValueError("Name must be lower cased")
    return value


@strawchemy.pydantic.create(Group, include="all")
class GroupCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]


@strawchemy.pydantic.create(User, include="all")
class UserCreateValidation:
    name: Annotated[str, AfterValidator(_check_lower_case)]
    group: GroupCreateValidation | None = strawberry.UNSET


@strawberry.type
class Mutation:
    create_user: UserType | ValidationErrorType = strawchemy.create(UserCreate, validation=UserCreateValidation)
```

> To get the validation errors exposed in the schema, you need to add `ValidationErrorType` in the field union type

When validation fails, the query will returns a `ValidationErrorType` with detailed error information from pydantic validation:

```graphql
mutation {
  createUser(data: { name: "Bob" }) {
    __typename
    ... on UserType {
      name
    }
    ... on ValidationErrorType {
      id
      errors {
        id
        loc
        message
        type
      }
    }
  }
}
```

```json
{
  "data": {
    "createUser": {
      "__typename": "ValidationErrorType",
      "id": "ERROR",
      "errors": [
        {
          "id": "ERROR",
          "loc": ["name"],
          "message": "Value error, Name must be lower cased",
          "type": "value_error"
        }
      ]
    }
  }
}
```

Validation also works with nested relationships:

```graphql
mutation {
  createUser(
    data: {
      name: "bob"
      group: {
        create: {
          name: "Group" # This will be validated
          tag: { set: { id: "..." } }
        }
      }
    }
  ) {
    __typename
    ... on ValidationErrorType {
      errors {
        loc
        message
      }
    }
  }
}
```

</details>

## Async Support

Strawchemy supports both synchronous and asynchronous operations. You can use either `StrawchemySyncRepository` or `StrawchemyAsyncRepository` depending on your needs:

```python
from strawchemy import StrawchemySyncRepository, StrawchemyAsyncRepository

# Synchronous resolver
@strawchemy.field
def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
    repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
    return repo.get_one_or_none()

# Asynchronous resolver
@strawchemy.field
async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
    repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
    return await repo.get_one_or_none()

# Synchronous mutation
@strawberry.type
class Mutation:
    create_user: UserType = strawchemy.create(
        UserCreateInput,
        repository_type=StrawchemySyncRepository
    )

# Asynchronous mutation
@strawberry.type
class AsyncMutation:
    create_user: UserType = strawchemy.create(
        UserCreateInput,
        repository_type=StrawchemyAsyncRepository
    )
```

By default, Strawchemy uses the StrawchemySyncRepository as its repository type. You can override this behavior by specifying a different repository using the `repository_type` configuration option.

## Configuration

Strawchemy can be configured when initializing the mapper.

### Configuration Options

| Option                     | Type                                                        | Default                    | Description                                                                                                                              |
| -------------------------- | ----------------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `session_getter`           | `Callable[[Info], Session]`                                 | `default_session_getter`   | Function to retrieve SQLAlchemy session from strawberry `Info` object. By default, it retrieves the session from `info.context.session`. |
| `auto_snake_case`          | `bool`                                                      | `True`                     | Automatically convert snake cased names to camel case in GraphQL schema.                                                                 |
| `repository_type`          | `type[Repository] \| StrawchemySyncRepository`              | `StrawchemySyncRepository` | Repository class to use for auto resolvers.                                                                                              |
| `filter_overrides`         | `OrderedDict[tuple[type, ...], type[SQLAlchemyFilterBase]]` | `None`                     | Override default filters with custom filters. This allows you to provide custom filter implementations for specific column types.        |
| `execution_options`        | `dict[str, Any]`                                            | `None`                     | SQLAlchemy execution options for repository operations. These options are passed to the SQLAlchemy `execution_options()` method.         |
| `pagination_default_limit` | `int`                                                       | `100`                      | Default pagination limit when `pagination=True`.                                                                                         |
| `pagination`               | `bool`                                                      | `False`                    | Enable/disable pagination on list resolvers by default.                                                                                  |
| `default_id_field_name`    | `str`                                                       | `"id"`                     | Name for primary key fields arguments on primary key resolvers.                                                                          |
| `dialect`                  | `Literal["postgresql"]`                                     | `"postgresql"`             | Database dialect to use. Currently, only PostgreSQL is supported.                                                                        |

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
