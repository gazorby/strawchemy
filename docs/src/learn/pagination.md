# Pagination

Pagination gives a list field `offset` and `limit` arguments, on root fields and on nested relationships alike.

## Paginating a list

```python
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(pagination=True)
```

`users` now takes `offset` and `limit` arguments, falling back to the config's defaults (limit 100 and offset 0 unless changed) whenever a query omits them or binds them to unset variables. `limit: null` lifts the limit:

```graphql
{
    users(offset: 0, limit: 10) {
        id
        name
    }
}
```

## Changing default page size

Pass a `DefaultOffsetPagination(limit=…, offset=…)` instead of `True` to override the config's defaults for this field alone, leaving every other paginated field on its own default:

```python
from strawchemy.schema.pagination import DefaultOffsetPagination


@strawberry.type
class Query:
    users_custom: list[UserType] = strawchemy.field(pagination=DefaultOffsetPagination(limit=20, offset=10))
```

`users_custom` now defaults to `limit: 20, offset: 10` for any query that omits them.

## Paginating relationships

Set `paginate="all"` on `@strawchemy.type` to add `offset`/`limit` arguments to every list relationship declared on that type:

```python
@strawchemy.type(User, include="all", paginate="all")  # [!code ++]
class UserType: ...
```

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

Pagination applies per parent row, and each alias of a relationship gets its own page. A relationship selected without `offset`/`limit`, or with them bound to unset variables, still gets its defaults; `default_pagination=DefaultOffsetPagination(…)` on `@strawchemy.type` changes them for that type's relationships. Rows tied on `orderBy` count one by one, and the database decides which of them a page keeps: MySQL and SQLite break ties by primary key on relationships; PostgreSQL may not. End `orderBy` on a unique field for stable pages.

::: warning
On SQLite and MySQL, a many-to-many relationship (one with a `secondary` table) cannot have its own ordering or pagination: the query fails with a `TranspilingError`. With `pagination="all"`, its default `limit` triggers the same error even when the client passes none.
:::

An `ORDER BY` added by a [query hook](/learn/query-hooks) sorts ahead of the client's `orderBy`, so it decides which rows each page keeps.

## Paginating everything

Set `pagination="all"` on `StrawchemyConfig` to add `offset`/`limit` to every list field across the schema, without opting in field by field:

```python
strawchemy = Strawchemy(
    StrawchemyConfig(
        "sqlite",
        repository_type=StrawchemyAsyncRepository,
        pagination="all",  # [!code focus]
        pagination_default_limit=100,
        pagination_default_offset=0,
    )
)


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field()
```

Every paginated field falls back to two defaults when a query omits `offset`/`limit`:

- `pagination_default_limit` — rows returned per page (100 unless changed).
- `pagination_default_offset` — rows skipped before the page starts (0 unless changed).
