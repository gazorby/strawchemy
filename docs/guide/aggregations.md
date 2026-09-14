# Aggregations

Strawchemy automatically exposes aggregation fields for list relationships.

When you define a model with a list relationship, the corresponding GraphQL type will include an aggregation field for
that relationship, named `<field_name>Aggregate`.

<details>
<summary> Basic aggregation example:</summary>

With the folliing model definitions:

```python
class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    author: Mapped[User] = relationship("User", back_populates="posts")
```

And the corresponding GraphQL types:

```python
@strawchemy.type(User, include="all")
class UserType:
    pass


@strawchemy.type(Post, include="all")
class PostType:
    pass
```

You can query aggregations on the `posts` relationship:

```graphql
{
    users {
        id
        name
        postsAggregate {
            count
            min {
                title
            }
            max {
                title
            }
            # Other aggregation functions are also available
        }
    }
}
```

</details>

## Filtering by relationship aggregations

You can also filter entities based on aggregations of their related entities.

<details>
<summary>Aggregation filtering example</summary>

Define types with filters:

```python
@strawchemy.filter(User, include="all")
class UserFilter:
    pass


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter)
```

For example, to find users who have more than 5 posts:

```graphql
{
    users(
        filter: {
            postsAggregate: { count: { arguments: [id], predicate: { gt: 5 } } }
        }
    ) {
        id
        name
        postsAggregate {
            count
        }
    }
}
```

You can use various predicates for filtering:

```graphql
# Users with exactly 3 posts
users(filter: {
postsAggregate: {
count: {
arguments: [id]
predicate: { eq: 3 }
}
}
})

# Users with posts containing "GraphQL" in the title
users(filter: {
postsAggregate: {
maxString: {
arguments: [title]
predicate: { contains: "GraphQL" }
}
}
})

# Users with an average post length greater than 1000 characters
users(filter: {
postsAggregate: {
avg: {
arguments: [contentLength]
predicate: { gt: 1000 }
}
}
})
```

</details>

### Distinct aggregations

<details>
<summary>Distinct aggregation filtering example</summary>

You can also use the `distinct` parameter to count only distinct values:

```graphql
{
    users(
        filter: {
            postsAggregate: {
                count: { arguments: [category], predicate: { gt: 2 }, distinct: true }
            }
        }
    ) {
        id
        name
    }
}
```

This would find users who have posts in more than 2 distinct categories.

</details>

### Fine-grained aggregation filters

`@strawchemy.aggregate_filter` declares a dedicated aggregation filter input for a relationship, the same way
`@strawchemy.filter` declares a column filter. It has two independent axes: `functions=` selects which aggregation
functions the input exposes, while `include`/`exclude` keep their usual column meaning and narrow which columns
*every* selected function is allowed to aggregate over.

<details>
<summary>Fine-grained aggregation filter example</summary>

```python
@strawchemy.aggregate_filter(
    Fruit, include=["id", "sweetness"], functions=["count", "sum"], name="FruitFineGrainedAggregateFilter"
)
class FruitFineGrainedAggregateFilter:
    # `count`'s predicate only exposes `gt`; its `arguments` enum still offers every column `include` allows.
    # The annotation is the value the predicate compares — `count` counts rows, so `int`.
    count: int = strawchemy.filter_field(ops=["gt"])
    # `sum` can only aggregate `sweetness`, and only accepts `gte` on its predicate.
    sum: float = strawchemy.filter_field(arguments=["sweetness"], ops=["gte"])


@strawchemy.filter(Color, include=["name", "fruits"], name="ColorFineGrainedFilter")
class ColorFineGrainedFilter:
    # Swaps the generated aggregate bool exp on `fruits_aggregate` for the declared one above.
    # Any other list relationship on `Color` would keep its full generated aggregate bool exp untouched.
    fruits_aggregate: FruitFineGrainedAggregateFilter


@strawberry.type
class Query:
    colors_fine_grained: list[ColorType] = strawchemy.field(filter_input=ColorFineGrainedFilter)
```

```graphql
{
    colorsFineGrained(
        filter: { fruitsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }
    ) {
        id
    }
}
```

</details>

Inside the class body, `strawchemy.filter_field()` refines one function at a time:

- **`ops`**: restricts that function's `predicate` to the given operators, the same way it does on a column filter.
- **`arguments`**: restricts that function's `arguments` enum to the given columns. These columns must already be
  within the decorator's own `include`/`exclude`; naming one outside that scope raises `StrawchemyFieldError` at
  definition time.
- A bare `strawchemy.filter_field()` force-includes a function that `functions=` left out — e.g. adding
  `avg = strawchemy.filter_field()` to the class above exposes `avg` even though
  `functions=["count", "sum"]` doesn't name it.

The annotation on a declared function names either the value its predicate compares (`int` for `count`, `float` for
`sum`, `avg` and the statistical functions, `datetime`/`date`/`time`/`str` for the typed `min`/`max` variants) or the
comparison input itself (`OrderComparison`). Anything else — including `Any` — raises `StrawchemyFieldError` at
import time, so an annotation always states something the factory has verified. A bare marker needs no annotation,
having nothing to describe.

Custom `apply=` filters are column-only: putting one on a function inside a class decorated with
`aggregate_filter` raises `StrawchemyFieldError`.

`functions=` values are the aggregation function's snake_case `field_name` (`count`, `sum`, `min`, `max`, `avg`,
`min_datetime`, `max_string`, ...), typed as `strawchemy.typing.AggregationFilterFunction` for editor completion.
The generated GraphQL *field* is camelCased as usual (e.g. `min_datetime` becomes `minDatetime`).

## Root aggregations

Strawchemy supports query level aggregations.

<details>
<summary>Root aggregations example:</summary>

First, create an aggregation type:

```python
@strawchemy.aggregate(User, include="all")
class UserAggregationType:
    pass
```

Then set up the root aggregations on the field:

```python
@strawberry.type
class Query:
    users_aggregations: UserAggregationType = strawchemy.field(root_aggregations=True)
```

Now you can use aggregation functions on the result of your query:

```graphql
{
    usersAggregations {
        aggregations {
            # Basic aggregations
            count

            sum {
                age
            }

            avg {
                age
            }

            min {
                age
                createdAt
            }
            max {
                age
                createdAt
            }

            # Statistical aggregations
            stddev {
                age
            }
            variance {
                age
            }
        }
        # Access the actual data
        nodes {
            id
            name
            age
        }
    }
}
```

</details>
