# Pagination

Strawchemy supports offset-based pagination out of the box.

<details>
<summary>Pagination examples</summary>

## Field-Level Pagination

Enable pagination on specific fields:

```python
from strawchemy.schema.pagination import DefaultOffsetPagination


@strawberry.type
class Query:
    # Enable pagination with default settings (limit=100, offset=0)
    users: list[UserType] = strawchemy.field(pagination=True)

    # Customize pagination defaults for this specific field
    users_custom: list[UserType] = strawchemy.field(pagination=DefaultOffsetPagination(limit=20, offset=10))
```

In your GraphQL queries, you can use the `offset` and `limit` parameters:

```graphql
{
    users(offset: 0, limit: 10) {
        id
        name
    }
}
```

## Config-Level Pagination

Enable pagination globally for all list fields:

```python
from strawchemy import Strawchemy, StrawchemyConfig

strawchemy = Strawchemy(
    StrawchemyConfig(
        "postgresql",
        pagination="all",  # Enable on all list fields
        pagination_default_limit=100,  # Default limit
        pagination_default_offset=0,  # Default offset
    )
)


@strawchemy.type(User, include="all")
class UserType:
    pass


@strawberry.type
class Query:
    # This field automatically has pagination enabled
    users: list[UserType] = strawchemy.field()
```

## Type-level pagination

Enable pagination for nested relationships from a specific type:

```python
@strawchemy.type(User, include="all", paginate="all")
class UserType:
    pass
```

Then in your GraphQL queries:

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

</details>
