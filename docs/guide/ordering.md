# Ordering

Strawchemy provides flexible ordering capabilities for query results.

<details>
<summary>Ordering examples</summary>

## Field-Level Ordering

Define ordering inputs and use them on specific fields:

```python
# Create order by input
@strawchemy.order(User, include="all")
class UserOrderBy:
    pass


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(order_by_input=UserOrderBy)
```

Query with ordering:

```graphql
{
    users(orderBy: [{ name: ASC }, { createdAt: DESC }]) {
        id
        name
        createdAt
    }
}
```

Available ordering options:

- `ASC` - Ascending order
- `DESC` - Descending order
- `ASC_NULLS_FIRST` - Ascending with nulls first
- `ASC_NULLS_LAST` - Ascending with nulls last
- `DESC_NULLS_FIRST` - Descending with nulls first
- `DESC_NULLS_LAST` - Descending with nulls last

## Type-Level Ordering

Enable ordering automatically on a type:

```python
@strawchemy.type(User, include="all", order="all")
class UserType:
    pass
```

This automatically generates and applies an order by input for all fields using this type.

## Config-Level Ordering

Enable ordering globally for all list fields:

```python
from strawchemy import Strawchemy, StrawchemyConfig

strawchemy = Strawchemy(
    StrawchemyConfig(
        "postgresql",
        order_by="all",  # Enable ordering on all list fields
    )
)


@strawchemy.type(User, include="all")
class UserType:
    pass


@strawberry.type
class Query:
    # This field automatically has ordering enabled
    users: list[UserType] = strawchemy.field()
```

With this configuration, all list fields will automatically have an `orderBy` argument without needing to specify it per
field.

## Nested Relationship Ordering

Order nested relationships:

```python
@strawchemy.type(User, include="all", order="all")
class UserType:
    pass
```

Query with nested ordering:

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

</details>
