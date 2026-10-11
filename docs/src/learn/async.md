# Async sessions

Strawchemy runs against a synchronous or an asynchronous SQLAlchemy session. This page shows how to switch a schema to async, write async resolvers, and mix both kinds of field.

Async sessions need the `asyncio` extra: `uv add "strawchemy[asyncio]"`.

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

## Concurrent reads

By default, every root field of a request runs on the request session, one after the other. Set
`read_session_getter` on `StrawchemyConfig` to give each read root field its own pooled session and
run those fields concurrently:

```python
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig

strawchemy = Strawchemy(
    StrawchemyConfig(
        "postgresql",
        repository_type=StrawchemyAsyncRepository,
        read_session_getter=lambda info: info.context["sessionmaker"](),  # [!code focus]
    )
)
```

The getter receives `Info`, so it can apply per-request setup such as a tenant `search_path` or a
read replica engine. Only async repositories run reads concurrently; sync repositories always use
the request session.

A read gets its own session only while the request session holds no pending writes. Once a
Strawchemy mutation or a `write_session` block writes to the request session, later reads stay on
that session and see the write. Committing the request session lets reads run concurrently again.
Query operations need nothing more, since graphql-core already resolves their root fields
concurrently.

### Custom resolvers

`strawchemy.read_session(info)` and `strawchemy.write_session(info)` apply the same rule in your own
resolvers. Mark a resolver that only reads with `read_only=True`:

```python
from sqlalchemy import func, select


@strawberry.type
class Query:
    @strawchemy.field(read_only=True)
    async def fruit_count(self, info: strawberry.Info) -> int:
        async with strawchemy.read_session(info) as session:
            return (await session.execute(select(func.count(Fruit.id)))).scalar_one()
```

Strawchemy trusts `read_only` without checking it. A repository can run on the yielded session:
`StrawchemyAsyncRepository(PostType, info, session=session)`. The sync variants are plain `with`
blocks and always yield the request session.

### Mutations

graphql-core runs the root fields of a mutation one after the other. Pass
`StrawchemyExecutionContext` to the schema to gather each run of consecutive read fields while
writes keep their order:

```python
from strawchemy import StrawchemyExecutionContext

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    execution_context_class=StrawchemyExecutionContext,  # [!code focus]
)
```

For `mutation { listColors getFruitById updateFruits listFruits updateColorById }`:

| Fields                       | Runs on                                        |
| ---------------------------- | ---------------------------------------------- |
| `listColors`, `getFruitById` | Two read sessions, concurrently                |
| `updateFruits`               | The request session                            |
| `listFruits`                 | The request session, so it sees `updateFruits` |
| `updateColorById`            | The request session                            |

Results come back in document order. A custom resolver without `read_only=True` runs alone and
splits the group. If you already subclass `ExecutionContext`, mix `StrawchemyExecutionContext` into
your subclass.

When a nullable read fails, the field resolves to `null` with an error and later fields still run.
When a non-null read fails, `data` becomes `null`, later root fields do not run, and Strawchemy
cancels the other concurrent reads. A failing `read_session_getter` or an exhausted pool raises a
field error on that field. Strawchemy closes every read session, whether its field succeeds, fails
or is cancelled.

### Pool size

Each concurrent read holds a connection. When only root fields open read sessions, a request uses
at most as many connections as its widest group of reads. Strawchemy sets no cap, so size
`pool_size` to match. Keep `read_session(info)` to root resolvers: in a nested resolver under a
list, it opens one session per parent item, all at once.

::: warning
- Concurrent reads use different connections and may see different snapshots if another
  transaction commits between them.
- Strawchemy misses a write flushed directly on the request session, such as
  `session.add(obj); await session.flush()` or `session.execute(update(...))` in a custom resolver,
  so later reads may not see it. Wrap such resolvers in `strawchemy.write_session(info)`, or commit
  the request session before the reads.
- The getter must return sessions on independent connections. An in-memory SQLite engine with
  `StaticPool` shares one connection and cannot serve concurrent reads.
:::
