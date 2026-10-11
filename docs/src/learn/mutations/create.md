# Create

`@strawchemy.create_input` builds an input type from a model; `strawchemy.create` turns it into a mutation field that inserts new records.

## Creating a record

```python
@strawchemy.create_input(Post, include=["title", "content", "views"])
class PostCreateInput: ...


@strawberry.type
class Mutation:
    create_post: PostType = strawchemy.create(PostCreateInput)
```

`createPost` takes one `data` object and returns the record it inserted:

```graphql
mutation {
    createPost(data: { title: "Hello", content: "My first post", views: 0 }) {
        id
        title
    }
}
```

## Creating several records

```python
@strawberry.type
class Mutation:
    create_post: PostType = strawchemy.create(PostCreateInput)
    create_posts: list[PostType] = strawchemy.create(PostCreateInput)  # [!code ++]
```

`createPosts` takes a list of `data` objects and inserts all of them in one operation:

```graphql
mutation {
    createPosts(
        data: [
            { title: "Hello", content: "My first post", views: 0 }
            { title: "GraphQL basics", content: "An intro to GraphQL", views: 0 }
        ]
    ) {
        id
        title
    }
}
```
