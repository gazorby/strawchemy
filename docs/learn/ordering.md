# Ordering

## Ordering a list

Let clients choose the sort order of any list field: pass an order-by type to `order_by_input` and the field gains an `orderBy` argument. `@strawchemy.order` builds that type from a model:

```python
@strawchemy.order(Post, include="all", override=True)
class PostOrderBy: ...


@strawberry.type
class Query:
    posts: list[PostType] = strawchemy.field(order_by_input=PostOrderBy)
```

```graphql
{
    posts(orderBy: [{ title: ASC }]) {
        id
        title
    }
}
```

## Ordering by several fields

`orderBy` takes a list, so a query can sort by more than one field at once — later entries break ties left by earlier ones:

```graphql
{
    posts(orderBy: [{ title: ASC }, { publishedAt: DESC }]) {
        id
        title
        publishedAt
    }
}
```

Each entry accepts one of six directions:

- `ASC` — ascending order.
- `DESC` — descending order.
- `ASC_NULLS_FIRST` — ascending, with nulls sorted first.
- `ASC_NULLS_LAST` — ascending, with nulls sorted last.
- `DESC_NULLS_FIRST` — descending, with nulls sorted first.
- `DESC_NULLS_LAST` — descending, with nulls sorted last.

An entry left empty (`{}`), or whose fields are all `null` or bound to unset variables, is skipped. An `orderBy` with no entry left falls back to the [default ordering](#default-ordering).

## Ordering relationships

Set `order="all"` on `@strawchemy.type` to give an `orderBy` argument to every list relationship declared on that type, not just the type itself:

```python
@strawchemy.type(User, include="all", order="all")  # [!code ++]
class UserType: ...
```

```graphql
{
    users(orderBy: [{ name: ASC }]) {
        id
        name
        posts(orderBy: [{ title: ASC }]) {
            id
            title
        }
    }
}
```

Each alias of a relationship takes its own arguments, so `newest: posts(orderBy: [{ publishedAt: DESC }])` and `oldest: posts(orderBy: [{ publishedAt: ASC }])` can sit side by side.

## Ordering by related rows

An `orderBy` entry can also sort by a relationship's fields, or by an aggregate of a list relationship through its `<field>Aggregate` input; to-one relationships have no aggregate input. None of these fields need to be selected, and relationships' own `orderBy` accepts the same entries:

```graphql
{
    posts(orderBy: [{ author: { name: ASC } }, { tagsAggregate: { count: DESC } }]) {
        title
    }
}
```

## Default ordering

`default_order_by` takes one or more SQLAlchemy ordering expressions, applied when a query sends no `orderBy`:

```python
@strawberry.type
class Query:
    posts: list[PostType] = strawchemy.field(order_by_input=PostOrderBy, default_order_by=Post.published_at.desc())
```

It orders that field's rows only; relationships selected under it don't inherit it. With neither `orderBy` nor `default_order_by`, `StrawchemyConfig.deterministic_ordering` (on unless changed) orders rows by primary key, and appends the primary key after a `default_order_by`.

An `ORDER BY` added by a [query hook](/learn/query-hooks) sorts ahead of all of these, including the client's `orderBy`, so it decides which rows a page keeps and which row `distinctOn` keeps from each group.

## Distinct rows

`distinct_on` adds a `distinctOn` argument that keeps one row per distinct value of the listed fields. `@strawchemy.distinct_on` builds its enum from a model:

```python
@strawchemy.distinct_on(Post, include="all")
class PostDistinctOn: ...


@strawberry.type
class Query:
    posts: list[PostType] = strawchemy.field(order_by_input=PostOrderBy, distinct_on=PostDistinctOn)
```

```graphql
{
    posts(distinctOn: [authorId], orderBy: [{ views: DESC }]) {
        title
        authorId
    }
}
```

The row kept from each group is the first one by `orderBy`, which need not start with the `distinctOn` fields — here, each author's most viewed post. `limit` and `offset` count the kept rows, and relationships selected under a kept row return all their rows. `distinct_on="all"` on `@strawchemy.type` adds `distinctOn` to its list relationships, where it applies per parent row.

PostgreSQL applies `DISTINCT ON` natively when the ordering starts with the `distinctOn` fields; otherwise, and always on MySQL and SQLite, it's emulated with a `row_number()` window, with the same results. On PostgreSQL, `json` columns are ordered and compared as `jsonb`.

## Ordering everything

Set `order_by="all"` on `StrawchemyConfig` to add `orderBy` to every list field across the schema, without opting in field by field:

```python
strawchemy = Strawchemy(
    StrawchemyConfig(
        "sqlite",
        repository_type=StrawchemyAsyncRepository,
        order_by="all",  # [!code focus]
    )
)


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field()
```
