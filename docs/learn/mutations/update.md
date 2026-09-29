# Update

`@strawchemy.pk_update_input` builds an input whose `id` field addresses the record to update; `strawchemy.update_by_ids` turns it into a mutation field.

## Updating by id

```python
@strawchemy.pk_update_input(Post, include=["id", "title"])
class PostUpdateInput: ...


@strawberry.type
class Mutation:
    update_post: PostType = strawchemy.update_by_ids(PostUpdateInput)
```

```graphql
mutation {
    updatePost(data: { id: 1, title: "Updated title" }) {
        id
        title
    }
}
```

## Updating several by id

Return `list[PostType]` instead of `PostType`, and `data` takes a list — each item updates the record whose id it carries:

```python
@strawberry.type
class Mutation:
    update_post: PostType = strawchemy.update_by_ids(PostUpdateInput)
    update_posts: list[PostType] = strawchemy.update_by_ids(PostUpdateInput)  # [!code ++]
```

```graphql
mutation {
    updatePosts(
        data: [
            { id: 1, title: "Updated title" }
            { id: 2, title: "Another title" }
        ]
    ) {
        id
        title
    }
}
```

## Updating by filter

`@strawchemy.filter_update_input` builds an input with no `id` field; `strawchemy.update` pairs it with a filter input instead, so one `data` payload is applied to every record the filter matches:

```python
@strawchemy.filter_update_input(Post, include=["title"])
class PostPartialInput: ...


@strawchemy.filter(Post, include="all")
class PostFilter: ...


@strawberry.type
class Mutation:
    update_posts_filter: list[PostType] = strawchemy.update(PostPartialInput, PostFilter)
```

```graphql
mutation {
    updatePostsFilter(data: { title: "Featured" }, filter: { views: { gt: 100 } }) {
        id
        title
    }
}
```

The filter takes the same input as a query filter, [related records](/learn/filtering#filtering-related-records) included; each matching record is updated once.
