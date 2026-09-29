# Delete

`strawchemy.delete()` turns into a mutation field that removes records. The returned data is the set of records that were deleted, so the same field selection used for a query works here too.

## Deleting by filter

Pass a filter input to `strawchemy.delete()` to remove only the records it matches:

```python
@strawchemy.filter(Post, include="all")
class PostFilter: ...


@strawberry.type
class Mutation:
    delete_posts_filter: list[PostType] = strawchemy.delete(PostFilter)
```

```graphql
mutation {
    deletePostsFilter(filter: { views: { lt: 10 } }) {
        id
        title
    }
}
```

The filter takes the same input as a query filter, [related records](/learn/filtering#filtering-related-records) included.

## Deleting everything

Leave out the filter argument and the mutation removes every record of the type instead:

```python
@strawberry.type
class Mutation:
    delete_posts_filter: list[PostType] = strawchemy.delete(PostFilter)
    delete_posts: list[PostType] = strawchemy.delete()  # [!code ++]
```

```graphql
mutation {
    deletePosts {
        id
        title
    }
}
```
