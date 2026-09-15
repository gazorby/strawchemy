# Strawchemy

[![🔂 Tests and linting](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/gazorby/strawchemy/graph/badge.svg?token=BCU8SX1MJ7)](https://codecov.io/gh/gazorby/strawchemy) [![PyPI Downloads](https://static.pepy.tech/badge/strawchemy)](https://pepy.tech/projects/strawchemy)

Strawchemy generates GraphQL types, inputs and resolvers from SQLAlchemy models. The models
already in the application are the schema definition.

Without it, filtering, ordering, pagination and nested selections all need hand-written
resolvers — boilerplate that also invites N+1 queries.

## Features

- 🔄 **Type Generation**: Generate strawberry types from SQLAlchemy models
- 🧠 **Smart Resolvers**: Automatically generates single, optimized database queries for a given GraphQL request
- 🔍 **Filtering**: Rich filtering capabilities on most data types, including PostGIS geo columns
- 📄 **Pagination**: Built-in offset-based pagination
- 📊 **Aggregation**: Support for aggregation functions like count, sum, avg, min, max, and statistical functions
- 🔀 **CRUD**: Full support for Create, Read, Update, Delete, and Upsert mutations with relationship handling
- 🪝 **Hooks**: Customize query behavior with query hooks: add filtering, load extra column etc.
- ⚡ **Sync/Async**: Works with both sync and async SQLAlchemy sessions
- 🛢 **Supported databases**: PostgreSQL ([asyncpg](https://github.com/MagicStack/asyncpg)/[psycopg3](https://www.psycopg.org/psycopg3/)), MySQL ([asyncmy](https://github.com/long2ice/asyncmy)), SQLite ([aiosqlite](https://aiosqlite.omnilib.dev/en/stable/)/[sqlite3](https://docs.python.org/3/library/sqlite3.html))

> [!Warning]
>
> Please note that strawchemy is currently in a pre-release stage of development. This means that the library is still
> under active development and the initial API is subject to change. We encourage you to experiment with strawchemy and
> provide feedback, but be sure to pin and update carefully until a stable release is available.

## Documentation

Full documentation is at **<https://strawchemy-docs.pages.dev>** — guides for
[mapping models](https://strawchemy-docs.pages.dev/learn/mapping-models),
[filtering](https://strawchemy-docs.pages.dev/learn/filtering),
[aggregations](https://strawchemy-docs.pages.dev/learn/aggregations) and
[mutations](https://strawchemy-docs.pages.dev/learn/mutations/), plus a generated
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

## A first look

Map a model, derive filter and type classes from it, then expose a query field:

```python
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list[Post]] = relationship("Post", back_populates="author")


strawchemy = Strawchemy(StrawchemyConfig("sqlite"))


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, pagination=True)
```

Querying it filters, paginates and resolves the `posts` relationship without any resolver code:

```graphql
{
    users(limit: 10, filter: { name: { contains: "Al" } }) {
        id
        name
        posts {
            title
        }
    }
}
```

See the [getting started guide](https://strawchemy-docs.pages.dev/learn/getting-started) for the full walkthrough.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this
project.

## License

This project is licensed under the terms of the license included in the [LICENCE](LICENCE) file.
