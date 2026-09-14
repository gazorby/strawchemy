# Strawchemy

[![🔂 Tests and linting](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/gazorby/strawchemy/graph/badge.svg?token=BCU8SX1MJ7)](https://codecov.io/gh/gazorby/strawchemy) [![PyPI Downloads](https://static.pepy.tech/badge/strawchemy)](https://pepy.tech/projects/strawchemy)

Generates GraphQL types, inputs, queries and resolvers directly from SQLAlchemy models.

## Features

- 🔄 **Type Generation**: Generate strawberry types from SQLAlchemy models

- 🧠 **Smart Resolvers**: Automatically generates single, optimized database queries for a given GraphQL request

- 🔍 **Filtering**: Rich filtering capabilities on most data types, including PostGIS geo columns

- 📄 **Pagination**: Built-in offset-based pagination

- 📊 **Aggregation**: Support for aggregation functions like count, sum, avg, min, max, and statistical functions

- 🔀 **CRUD**: Full support for Create, Read, Update, Delete, and Upsert mutations with relationship handling

- 🪝 **Hooks**: Customize query behavior with query hooks: add filtering, load extra column etc.

- ⚡ **Sync/Async**: Works with both sync and async SQLAlchemy sessions

- 🛢 **Supported databases**:
    - PostgreSQL (using [asyncpg](https://github.com/MagicStack/asyncpg)
      or [psycopg3 sync/async](https://www.psycopg.org/psycopg3/))
    - MySQL (using [asyncmy](https://github.com/long2ice/asyncmy))
    - SQLite (using [aiosqlite](https://aiosqlite.omnilib.dev/en/stable/)
      or [sqlite](https://docs.python.org/3/library/sqlite3.html))

> [!Warning]
>
> Please note that strawchemy is currently in a pre-release stage of development. This means that the library is still
> under active development and the initial API is subject to change. We encourage you to experiment with strawchemy and
> provide feedback, but be sure to pin and update carefully until a stable release is available.

## Documentation

Full documentation is at **<https://strawchemy-docs.pages.dev>** — guides for
[mapping models](https://strawchemy-docs.pages.dev/guide/mapping-models),
[filtering](https://strawchemy-docs.pages.dev/guide/filtering),
[aggregations](https://strawchemy-docs.pages.dev/guide/aggregations) and
[mutations](https://strawchemy-docs.pages.dev/guide/mutations/), plus a generated
[API reference](https://strawchemy-docs.pages.dev/reference/api/mapper).

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
strawchemy = Strawchemy("postgresql")


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


# override=True is needed because strawchemy automatically generates a PostType
# when mapping UserType due to the relationship between User and Post
@strawchemy.type(Post, include="all", override=True)
class PostType:
    pass


# Create filter inputs
@strawchemy.filter(User, include="all")
class UserFilter:
    pass


# override=True is needed for the same reason as PostType
@strawchemy.filter(Post, include="all", override=True)
class PostFilter:
    pass


# Create order by inputs
@strawchemy.order(User, include="all")
class UserOrderBy:
    pass


@strawchemy.order(Post, include="all", override=True)
class PostOrderBy:
    pass


# Define GraphQL query fields
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
    posts: list[PostType] = strawchemy.field(filter_input=PostFilter, order_by_input=PostOrderBy, pagination=True)


# Create schema
schema = strawberry.Schema(query=Query)
```

See the [getting started guide](https://strawchemy-docs.pages.dev/guide/getting-started) for the full walkthrough,
including the generated GraphQL queries.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this
project.

## License

This project is licensed under the terms of the license included in the [LICENCE](LICENCE) file.
