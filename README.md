# Strawchemy

[![🔂 Tests and linting](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/gazorby/strawchemy/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/gazorby/strawchemy/graph/badge.svg?token=BCU8SX1MJ7)](https://codecov.io/gh/gazorby/strawchemy) [![PyPI Downloads](https://static.pepy.tech/badge/strawchemy)](https://pepy.tech/projects/strawchemy)

Strawchemy generates GraphQL types, inputs and resolvers from SQLAlchemy models. The models
already in the application are the schema definition.

Without it, filtering, ordering, pagination and nested selections all need hand-written
resolvers — boilerplate that also invites N+1 queries.

## Features

- **Single-statement resolution**\
  Each root field's selection set compiles to one SQL query, however deep. No dataloaders, no N+1.
- **Type-aware filtering**\
  Each column gets the comparisons its type supports, from text and dates to arrays, JSON, and PostGIS geometry, combined with and, or, and not to any depth.
- **Full aggregation support**\
  Aggregate a relationship or the whole result set, and filter on the result — "users with more than three posts" is a filter argument.
- **Nested mutation trees**\
  Create a parent, its children and their children in one mutation. Link, unlink and insert-or-update in the same call.
- **Generated GraphQL types**\
  Output types and the filtering, ordering, and mutation inputs all come from the model, and you opt into each separately.
- **Layered configuration**\
  Set defaults once on the mapper, override them on a type, and override them again on a single field.
- **Custom fields**\
  A field you write yourself declares what it reads, and the main query loads it.
- **Multi-dialect**\
  Target PostgreSQL, MySQL, and SQLite from one mapping; Strawchemy absorbs the dialect differences.
- **Sync/Async compatible**\
  The same mapped types work against a sync or an async session, chosen per schema or per field.

> [!Warning]
>
> Please note that strawchemy is currently in a pre-release stage of development. This means that the library is still
> under active development and the initial API is subject to change. We encourage you to experiment with strawchemy and
> provide feedback, but be sure to pin and update carefully until a stable release is available.

## Documentation

Full documentation is at **<https://strawchemy.pages.dev>** — guides for
[mapping models](https://strawchemy.pages.dev/learn/mapping-models),
[filtering](https://strawchemy.pages.dev/learn/filtering),
[aggregations](https://strawchemy.pages.dev/learn/aggregations) and
[mutations](https://strawchemy.pages.dev/learn/mutations/), plus a generated
[API reference](https://strawchemy.pages.dev/reference/api/mapper).

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

See the [getting started guide](https://strawchemy.pages.dev/learn/getting-started) for the full walkthrough.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this
project.

## License

This project is licensed under the terms of the license included in the [LICENCE](LICENCE) file.
