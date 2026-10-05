# Async sessions

Strawchemy runs against a synchronous or an asynchronous SQLAlchemy session. This page shows how to switch a schema to async, write async resolvers, and mix both kinds of field.

## Async repository

Set `repository_type` on `StrawchemyConfig` to make every generated field run async. This option
decides whether a schema's fields run through `StrawchemySyncRepository` or
`StrawchemyAsyncRepository`:

```python
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig

strawchemy = Strawchemy(
    StrawchemyConfig(
        "sqlite",
        repository_type=StrawchemyAsyncRepository,  # [!code focus]
    )
)
```

Left unset, `repository_type` defaults to `StrawchemySyncRepository`, so an async session needs it set explicitly.

::: warning
`repository_type` and the session it runs against must agree. A schema left at the sync
default, run against an async session, builds without complaint — the mismatch surfaces only once
a request executes a query, as a `GraphQLError` in the response:

```
'coroutine' object has no attribute 'all'
```

The sync repository passes the session's `execute()` result straight to code that expects rows
back; against an async session that result is an unawaited coroutine. Set
`repository_type=StrawchemyAsyncRepository` on `StrawchemyConfig` whenever the session is async.
:::

## Async resolvers

A hand-written resolver picks its own repository class, so it must match the session it runs on.
Here is `get_post_by_title` from [custom resolvers](/learn/resolvers), sync and async:

:::code-group

```python [Sync]
from sqlalchemy import select
from strawchemy import StrawchemySyncRepository


@strawberry.type
class Query:
    @strawchemy.field
    def get_post_by_title(self, info: strawberry.Info, title: str) -> PostType | None:
        repo = StrawchemySyncRepository(PostType, info, filter_statement=select(Post).where(Post.title == title))
        return repo.get_one_or_none().graphql_type_or_none()
```

```python [Async]
from sqlalchemy import select
from strawchemy import StrawchemyAsyncRepository


@strawberry.type
class Query:
    @strawchemy.field
    async def get_post_by_title(self, info: strawberry.Info, title: str) -> PostType | None:
        repo = StrawchemyAsyncRepository(PostType, info, filter_statement=select(Post).where(Post.title == title))
        return (await repo.get_one_or_none()).graphql_type_or_none()
```

:::

The async form adds `async` to the resolver, awaits the repository call, and constructs
`StrawchemyAsyncRepository` in place of `StrawchemySyncRepository`; the rest of the resolver
stays the same.

## Mixing sync and async

Every field factory — `strawchemy.field`, `strawchemy.create`, `strawchemy.update`, and the rest —
accepts `repository_type`, overriding the schema-wide default for that one field. A schema left at
the sync default can still run a single mutation against an async session:

```python
from strawchemy import StrawchemyAsyncRepository


@strawberry.type
class Mutation:
    create_post: PostType = strawchemy.create(PostCreateInput, repository_type=StrawchemyAsyncRepository)
```

Every other field on `Query` and `Mutation` still runs through `StrawchemySyncRepository`; only
`create_post` needs an async session.
