# Strawchemy

A SQLAlchemy model and a two-line mapped type buy filtering, ordering, pagination and
aggregations against it, all resolved in one SQL query however deep the selection. The same
mapping adds nested create and update mutations.

## The difference it makes

Take a query for `users`, filtered by name and paginated, with each user's `posts` nested
inside.

:::code-group

```python [Strawchemy]
strawchemy = Strawchemy(StrawchemyConfig("sqlite"))


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, pagination=True)
```

```python [Plain Strawberry]
@strawberry.type
class PostType:
    id: int
    title: str


@strawberry.type
class UserType:
    id: int
    name: str

    @strawberry.field
    async def posts(self, info: strawberry.Info) -> list[PostType]:
        session: AsyncSession = info.context.session
        result = await session.execute(select(Post).where(Post.author_id == self.id))
        return [PostType(id=post.id, title=post.title) for post in result.scalars()]


@strawberry.type
class Query:
    @strawberry.field
    async def users(self, info: strawberry.Info, limit: int = 10, name_contains: str | None = None) -> list[UserType]:
        session: AsyncSession = info.context.session
        statement = select(User).limit(limit)
        if name_contains is not None:
            statement = statement.where(User.name.contains(name_contains))
        result = await session.execute(statement)
        return [UserType(id=user.id, name=user.name) for user in result.scalars()]
```

:::

A hand-written `posts` resolver has no visibility into the other users on the page, so it runs
its own query for each one: one statement for the page of users, then one more per user
returned. Ten users is eleven round trips. Strawchemy resolves the same query as one SQL
statement — a join for `posts`, with `LIMIT` applied inside a subquery over the root `user` rows
so pagination counts users rather than joined rows. No dataloader, because there's no second
query to batch.

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
- **SQLAlchemy 2.0 and 2.1**\
  Runs on either release line, with type annotations that follow the installed version.

::: warning
Strawchemy is in pre-release and under active development, and its initial API may change. We
encourage you to experiment with strawchemy and provide feedback, but pin and update carefully
until a stable release is available.
:::

## Next steps

- [Getting started](/learn/getting-started)
- [Strawchemy and Strawberry](/learn/strawchemy-and-strawberry)
- [Architecture](/learn/architecture)
