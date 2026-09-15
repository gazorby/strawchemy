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

## Date and time parts

Filter a `Date`, `DateTime`, `Time` or `Interval` column by one of its components — year, month, hour, and so on, listed in the operator table above — instead of comparing the whole value:

```graphql
{
    posts(filter: { publishedAt: { year: 2024, month: 6 } }) {
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

You can also go the other way: force-include a field the decorator's `include`/`exclude` would otherwise have dropped, with its full default comparison, by leaving `ops` and `apply` both out — and no annotation:

```python
class PostFineGrainedFilter:
    content = strawchemy.filter_field()
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

The callable's signature is `(statement, value, *, dialect, model) -> Select`: it receives an isolated `select(model)` statement and the GraphQL-supplied value, and must only add `.where(...)` predicates to it. It must not join or subquery against the same model — the statement is later re-aliased and correlated back to the outer query by primary key, and a self-join there could be rewritten ambiguously. `join` picks that correlation strategy: `"exists"` (the default) wraps it in a correlated `EXISTS`; `"in"` folds it back with an `IN` against the primary key instead.

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
