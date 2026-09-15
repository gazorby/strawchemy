# Aggregations

## Aggregating a relationship

Every list relationship Strawchemy maps gets an automatic `<field>Aggregate` field on its
GraphQL type — no extra declaration needed.

```graphql
{
    users {
        name
        posts {
            title
        }
        postsAggregate {
            count
            min {
                title
            }
            max {
                title
            }
        }
    }
}
```

## Filtering by an aggregate

You can also filter entities by an aggregate of their related rows — for example, users with
more than 5 posts. Wire up a filter the same way you would for a column, and the relationship's
aggregate comes along with it. `users` here is unpaginated:

```python
@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

```graphql
{
    users(
        filter: { postsAggregate: { count: { arguments: [id], predicate: { gt: 5 } } } }
    ) {
        name
        posts {
            title
        }
        postsAggregate {
            count
        }
    }
}
```

## Counting distinct values

The same `users` field, filtered on users whose posts cover more than 2 distinct titles:

```graphql
{
    users(
        filter: {
            postsAggregate: { count: { arguments: [title], predicate: { gt: 2 }, distinct: true } }
        }
    ) {
        name
        posts {
            title
        }
        postsAggregate {
            count
        }
    }
}
```

## Restricting functions

By default, a generated aggregate filter exposes every supported function for every included
column. `@strawchemy.aggregate_filter` declares a dedicated aggregation filter input for a
relationship instead, the same way `@strawchemy.filter` declares a column filter. It has two
independent axes: `functions=` selects which aggregation functions the input exposes, while
`include`/`exclude` keep their usual column meaning and narrow which columns *every* selected
function is allowed to aggregate over.

```python
@strawchemy.aggregate_filter(
    Post, include=["id", "views"], functions=["count", "sum"], name="PostFineGrainedAggregateFilter"
)
class PostFineGrainedAggregateFilter:
    count: int = strawchemy.filter_field(ops=["gt"])
    sum: float = strawchemy.filter_field(arguments=["views"], ops=["gte"])


@strawchemy.filter(User, include=["name", "posts"], name="UserFineGrainedFilter")
class UserFineGrainedFilter:
    posts_aggregate: PostFineGrainedAggregateFilter


@strawberry.type
class Query:
    users_fine_grained: list[UserType] = strawchemy.field(filter_input=UserFineGrainedFilter)
```

```graphql
{
    usersFineGrained(
        filter: { postsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }
    ) {
        id
    }
}
```

`posts_aggregate: PostFineGrainedAggregateFilter` swaps the generated aggregate bool expression on
that one field for the declared one above; any other list relationship on `User` keeps its full
generated aggregate bool expression untouched.

Inside the class body, `strawchemy.filter_field()` refines one function at a time:

- **`ops`**: restricts that function's `predicate` to the given operators, the same way it does on a column filter.
- **`arguments`**: restricts that function's `arguments` enum to the given columns. These columns must already be
  within the decorator's own `include`/`exclude`; naming one outside that scope raises `StrawchemyFieldError` at
  definition time.
- A bare `strawchemy.filter_field()` force-includes a function that `functions=` left out — e.g. adding
  `avg = strawchemy.filter_field()` to the class above exposes `avg` even though
  `functions=["count", "sum"]` doesn't name it.

`functions=` values are the aggregation function's snake_case `field_name` (`count`, `sum`, `min`, `max`, `avg`,
`min_datetime`, `max_string`, ...), typed as `strawchemy.typing.AggregationFilterFunction` for editor completion.
The generated GraphQL *field* is camelCased as usual (e.g. `min_datetime` becomes `minDatetime`).

::: warning
The annotation on a declared function names either the value its predicate compares (`int` for `count`, `float` for
`sum`, `avg` and the statistical functions, `datetime`/`date`/`time`/`str` for the typed `min`/`max` variants) or the
comparison input itself (`OrderComparison`). Anything else — including `Any` — raises `StrawchemyFieldError` at
import time, so an annotation always states something the factory has verified. A bare marker needs no annotation,
having nothing to describe.

Custom `apply=` filters are column-only: putting one on a function inside a class decorated with
`aggregate_filter` raises `StrawchemyFieldError`.
:::

## Aggregating a result set

You can also aggregate an entire list at the query root, without filtering by any of it — total
count, sums, extremes — alongside the matching rows themselves.

```python
@strawchemy.aggregate(Post, include="all")
class PostAggregationType: ...


@strawberry.type
class Query:
    posts_aggregations: PostAggregationType = strawchemy.field(root_aggregations=True)
```

```graphql
{
    postsAggregations {
        aggregations {
            count

            sum {
                views
            }

            avg {
                views
            }

            min {
                views
                publishedAt
            }
            max {
                views
                publishedAt
            }
        }
        nodes {
            id
            title
        }
    }
}
```

::: warning
`stddevSamp`, `stddevPop`, `varSamp` and `varPop` exist on PostgreSQL and MySQL but not on SQLite —
the dialect this running example uses. Each dialect's supported aggregation functions
narrow which of these fields the schema actually generates; requesting one your dialect doesn't
support is a GraphQL validation error.
:::
