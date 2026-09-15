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
