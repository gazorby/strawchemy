# Filtering

## Filtering a list

Let clients narrow any list field down to the rows they want: pass a filter type to `filter_input` and the field gains a `filter` argument. `@strawchemy.filter` builds that type from a model:

```python
@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

A filter argument accepts several operators at once on the same field — every key in the filter object must match, as in `{ id: { gt: 1, lte: 100 } }`:

```graphql
{
    users(filter: { id: { gt: 1, lte: 100 } }) {
        id
        name
    }
}
```

Strawchemy supports a wide range of filter operations:

| Data Type/Category                      | Filter Operations                                                                                                                                                                |
|-----------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
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

`like`, `nlike`, `ilike` and `nilike` take a SQL `LIKE` pattern: `%` matches any sequence of characters, `_` any single character, and a backslash makes the next character literal (`\%`, `\_`, `\\`; written `"50\\%"` in a GraphQL string). A pattern ending with a lone backslash raises `FilterValueError` before the query runs, and the client gets a GraphQL error: `LIKE pattern '50\\' must not end with an escape character`. `startswith`, `endswith`, `contains` and their `i` variants match their value literally. Without the `i` prefix, these operators and `regexp`, `nregexp` compare letter case on every database, SQLite and MySQL included; with it, they ignore case, of non-ASCII letters too for the `LIKE`-based ones. The `LIKE`-based operators compare accents and trailing spaces on every database, whatever the column collation. `regexp` and its variants match anywhere in the value, in the database's own regular expression syntax (Python's `re` on SQLite).

`in: []` matches no rows and `nin: []` every row.

`hasKey`, `hasKeyAll` and `hasKeyAny` match the top-level keys of a JSON object, read literally: `hasKey: "a.b"` matches `{"a.b": 1}`, not `{"a": {"b": 1}}`, and a key holding `null` counts. Arrays and scalars have no keys. `hasKeyAll: []` matches every row, `hasKeyAny: []` none. On PostgreSQL, JSON filters work on `json` and `jsonb` columns alike. On SQLite, JSON columns have no `contains` or `containedIn` filter.

PostGIS geometry columns filter too, with their own operations — see [geometry](/learn/geometry).

## Combining conditions

Combine several field conditions into one filter with three logical operators:

- `_and` — every nested condition must match (the same as putting multiple keys directly on one filter object)
- `_or` — at least one nested condition must match
- `_not` — negates a single nested condition

```graphql
{
    users(filter: { _or: [{ name: { eq: "Alice" } }, { name: { eq: "Bob" } }] }) {
        id
        name
    }
}
```

`_not` matches exactly the rows its condition does not, rows with a `NULL` column included: `_not: { bio: { eq: "x" } }` returns users without a bio, where `bio: { neq: "x" }` does not.

An empty filter is ignored, as if it were absent: `{}`, a filter field set to `null` (`name: null`, `group: null`, `_not: null`), a comparison with no operator set (`name: {}`, or operators set to `null` or bound to omitted variables), and a relationship or aggregation filter holding only empty filters (`group: {}`, `group: { name: {} }`, `postsAggregate: { count: { arguments: [id], predicate: {} } }`) match every row, including rows without a related row. An empty `_or` branch is dropped rather than matching every row: `_or: [{}, { name: { eq: "John" } }]` is the same as `name: { eq: "John" }`, and an `_or` with only empty branches filters nothing. This also applies under `_not` and to mutations filtering the rows to update or delete. Use `isNull`, not `eq: null`, to test for `NULL`.

## Filtering related records

```graphql
{
    users(filter: { posts: { title: { contains: "GraphQL" } } }) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

The filter selects users, not posts: each matching user appears once, on paginated fields too, and `posts` lists all of its posts, not only the matching ones.

On a to-many relationship, one filter object must match a single related row, `_and` inside it included: `posts: { title: { contains: "GraphQL" }, views: { gt: 10 } }` needs one post matching both. Separate filters on the same relationship, as in `_and: [{ posts: { title: { contains: "GraphQL" } } }, { posts: { views: { gt: 10 } } }]`, may each match a different post. `_not: { posts: { ... } }` matches users with no matching post; `posts: { _not: { ... } }` those with at least one post that does not match.

A relationship filter that holds a predicate only matches rows that have a matching related row, whatever the filters next to it: `users(filter: { group: { name: { isNull: true } } })` skips users without a group. To find rows without a related row, filter on the foreign key column (`groupId: { isNull: true }`), negate the relationship (`_not: { group: { id: { isNull: false } } }`) or, for to-many relationships, count them (`postsAggregate: { count: { arguments: [id], predicate: { eq: 0 } } }`). Update and delete mutations filter on relationships with the same rules.

## Date and time parts

Filter a `Date`, `DateTime`, `Time` or `Interval` column by one of its components — year, month, hour, and so on, listed in the operator table above — instead of comparing the whole value:

```graphql
{
    posts(filter: { publishedAt: { year: { eq: 2024 }, month: { eq: 6 } } }) {
        id
        title
        publishedAt
    }
}
```

## Restricting operators

By default, `@strawchemy.filter` exposes every operator for every included column. A class body overrides that, field by field. Below, `title` is restricted to `eq` and `like`:

```python
from strawchemy import TextComparison


@strawchemy.filter(Post, include=["id", "title", "views"], name="PostFineGrainedFilter")
class PostFineGrainedFilter:
    title: TextComparison = strawchemy.filter_field(ops=["eq", "like"])


@strawberry.type
class Query:
    posts_fine_grained: list[PostType] = strawchemy.field(filter_input=PostFineGrainedFilter)
```

Operators left out are absent from the generated GraphQL input entirely, not merely rejected at runtime. Querying `title` with `contains` — never declared in `ops` — fails GraphQL validation before the request reaches a resolver:

```graphql
{
    postsFineGrained(filter: { title: { contains: "Hello" } }) { # [!code error]
        id
        title
    }
}
```

```
Field 'contains' is not defined by type 'TextComparisonStrEqLike'.
```

`ops` values are typed: `strawchemy` exports one operator alias per comparison input — `EqualityOperator`, `OrderOperator`, `TextOperator`, `ArrayOperator`, `DateOperator`, `TimeOperator`, `DateTimeOperator`, `TimeDeltaOperator` — plus `ComparisonOperator` for their union, which is what `ops=` accepts. A typo is a type error, and you can name a vocabulary yourself (`MY_OPS: list[TextOperator] = ["eq", "like"]`). Which operators a given field actually accepts still depends on its column or aggregation function, and that narrower check happens when the filter class is built. `ops=` does not apply to JSON or geo columns: their comparisons declare operators outside the registry these aliases mirror.

::: warning
On an `ops` field the annotation names either the column's data type (`str` for `title`) or the column's comparison input (`TextComparison`); anything else — including `Any` — raises `StrawchemyFieldError` at import time.
:::

You can also go the other way: force-include a field the decorator's `include`/`exclude` would otherwise have dropped, with its full default comparison, by leaving `ops` and `apply` both out:

```python
class PostFineGrainedFilter:
    content: str = strawchemy.filter_field()
```

## Non-column filters

Add a filter backed by no column at all with `apply=`: a callable that adds its own `WHERE` predicate to an isolated `select(Post)` statement, driven by whatever value the client passes. Add `more_viewed_than` to the filter above as a virtual scalar field, and reuse the same callable for `more_viewed_than_in` with `join="in"` — a different correlation strategy for the same predicate:

```python
from typing import Any

from sqlalchemy import Select


def _post_more_viewed_than(statement: Select[tuple[Post]], value: int, **_ctx: Any) -> Select[tuple[Post]]:
    return statement.where(Post.views >= value)


@strawchemy.filter(Post, include=["id", "title", "views"], name="PostFineGrainedFilter")
class PostFineGrainedFilter:
    title: TextComparison = strawchemy.filter_field(ops=["eq", "like"])
    more_viewed_than: int = strawchemy.filter_field(apply=_post_more_viewed_than)  # [!code ++]
    more_viewed_than_in: int = strawchemy.filter_field(apply=_post_more_viewed_than, join="in")  # [!code ++]
```

```graphql
{
    postsFineGrained(filter: { moreViewedThan: 5 }) {
        id
        views
    }
}
```

`ops` and `apply` are mutually exclusive on the same field.

The callable's signature is `(statement, value, *, dialect, model) -> Select`: it receives an isolated `select(model)` statement and the GraphQL-supplied value, and must only add `.where(...)` predicates to it. A `null` value skips the filter: `apply` never receives `None`. It must not join or subquery against the same model — the statement is later re-aliased and correlated back to the outer query by primary key, and a self-join there could be rewritten ambiguously. `join` picks that correlation strategy: `"exists"` (the default) wraps it in a correlated `EXISTS`; `"in"` folds it back with an `IN` against the primary key instead.

::: warning
An `apply` field is different: it has no column, so its annotation *defines* the generated GraphQL input type (`more_viewed_than: int` above) and is used verbatim.
:::

These `strawberry.field` keyword arguments — `name`, `description`, `deprecation_reason`, `metadata`, `directives` — pass straight through to the generated field:

```python
class PostFineGrainedFilter:
    title: TextComparison = strawchemy.filter_field(
        ops=["eq"], name="postTitle", description="Filter by post title", deprecation_reason="use `id` instead"
    )
```
