# Getting started

This page builds a working GraphQL API over three SQLAlchemy models, served by Litestar on
SQLite. By the end, you'll have a running server and a query you can execute against it. The
code lives in a `quickstart` package with four modules built up over the next steps:
`models.py`, `types.py`, `schema.py`, and `app.py`.

## Installation

```console
uv add strawchemy "litestar[sqlalchemy,standard]" aiosqlite strawberry-graphql
```

`strawchemy[geo]` adds PostGIS support through [GeoAlchemy2](https://github.com/geoalchemy/geoalchemy2).

## Models

A user writes posts, and posts carry tags through an association table:

:::code-group

```python [models.py]
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


post_tag = Table(
    "post_tag",
    Base.metadata,
    Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]
    posts: Mapped[list[Post]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    views: Mapped[int] = mapped_column(default=0)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), default=None)
    author: Mapped[User | None] = relationship("User", back_populates="posts")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary=post_tag, back_populates="posts")


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list[Post]] = relationship("Post", secondary=post_tag, back_populates="tags")
```

:::

## GraphQL mapping

Start with the mapper and the three `@strawchemy.type` classes:

:::code-group

```python [types.py]
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig

from quickstart.models import Post, Tag, User

strawchemy = Strawchemy(StrawchemyConfig("sqlite", repository_type=StrawchemyAsyncRepository))


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.type(Post, include="all", override=True)
class PostType: ...


@strawchemy.type(Tag, include="all", override=True)
class TagType: ...
```

:::

- The mapper's dialect is `sqlite`.
- `repository_type` must be `StrawchemyAsyncRepository` because the session used below is async —
  the default is `StrawchemySyncRepository`.
- `override=True` is needed on `PostType` and `TagType` because mapping `UserType` already
  generated types for the related `Post` and `Tag` models, and again below for `PostFilter` and
  `PostOrderBy` since mapping `UserFilter` and `UserOrderBy` does the same.

## Filtering and sorting

Add filter and order-by inputs for each model:

:::code-group

```python [types.py]
@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.filter(Post, include="all", override=True)
class PostFilter: ...


@strawchemy.order(User, include="all")
class UserOrderBy: ...


@strawchemy.order(Post, include="all", override=True)
class PostOrderBy: ...
```

:::

These become the `filter` and `orderBy` arguments on the GraphQL fields.

## Building the schema

:::code-group

```python [schema.py]
import strawberry

from quickstart.types import PostFilter, PostOrderBy, PostType, UserFilter, UserOrderBy, UserType, strawchemy


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
    posts: list[PostType] = strawchemy.field(filter_input=PostFilter, order_by_input=PostOrderBy, pagination=True)


schema = strawberry.Schema(query=Query)
```

:::

## Serving the API

Wire the schema into a Litestar app:

:::code-group

```python [app.py]
from __future__ import annotations

from typing import TYPE_CHECKING

from litestar import Litestar
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from strawberry.litestar import BaseContext, make_graphql_controller

from quickstart.models import Base
from quickstart.schema import schema

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///quickstart.sqlite",
    create_all=True,
    metadata=Base.metadata,
)


class GraphQLContext(BaseContext):
    session: AsyncSession


async def context_getter(db_session: AsyncSession) -> GraphQLContext:
    return GraphQLContext(db_session)


def create_app() -> Litestar:
    return Litestar(
        plugins=[SQLAlchemyPlugin(config=config)],
        route_handlers=[make_graphql_controller(schema, context_getter=context_getter)],
    )
```

:::

`context_getter` is what `session_getter` reads the session from. Run the server:

```console
uv run litestar --app quickstart.app:create_app run --reload
```

Open `http://127.0.0.1:8000/graphql` to reach GraphiQL.

::: tip
The complete project is in `examples/quickstart` in the repository.
:::

## Querying

```graphql
{
    users(limit: 10, filter: { name: { contains: "Al" } }, orderBy: { name: ASC }) {
        id
        name
        posts {
            title
            views
        }
    }
}
```

The database starts empty, so querying it now returns `{"data": {"users": []}}`. Once a `User`
row named "Alice" exists with a `Post` titled "Hello", the same query returns:

```json
{
  "data": {
    "users": [
      {
        "id": 1,
        "name": "Alice",
        "posts": [{ "title": "Hello", "views": 3 }]
      }
    ]
  }
}
```

## Writing data

Add a create input to `types.py`, then wire it into a new `Mutation` type in `schema.py` — add
`PostCreateInput` to its import from `quickstart.types`:

:::code-group

```python [types.py]
@strawchemy.create_input(Post, include=["title", "content", "views"])  # [!code ++]
class PostCreateInput: ...  # [!code ++]
```

```python [schema.py]
@strawberry.type  # [!code ++]
class Mutation:  # [!code ++]
    create_post: PostType = strawchemy.create(PostCreateInput)  # [!code ++]


schema = strawberry.Schema(query=Query, mutation=Mutation)  # [!code ++]
```

:::

```graphql
mutation {
    createPost(data: { title: "Hello", content: "My first post", views: 0 }) {
        id
        title
    }
}
```

## Next steps

- [Mapping models](/learn/mapping-models)
- [Queries](/learn/queries)
- [Filtering](/learn/filtering)
- [Mutations](/learn/mutations/)
