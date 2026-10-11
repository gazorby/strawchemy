# Nested update

An update mutation can change a relationship alongside the record itself, using the same `auto`-declared fields as a create mutation.

## Replacing a relationship

`author: auto` on `PostUpdateWithAuthorInput` lets `updatePostWithAuthor` point the post at a different existing user, with `set`:

```python
from strawberry import auto


@strawchemy.pk_update_input(Post, include=["id", "title"])
class PostUpdateWithAuthorInput:
    author: auto


@strawberry.type
class Mutation:
    update_post_with_author: PostType = strawchemy.update_by_ids(PostUpdateWithAuthorInput)
```

```graphql
mutation {
    updatePostWithAuthor(data: { id: 1, title: "Updated title", author: { set: { id: 2 } } }) {
        id
        title
        author {
            id
            name
        }
    }
}
```

`set: null` clears the relationship instead:

```graphql
mutation {
    updatePostWithAuthor(data: { id: 1, title: "No author", author: { set: null } }) {
        id
        title
        author {
            id
        }
    }
}
```

`set` on a to-many field works the same way, replacing the whole collection with the posts named by id:

```python
@strawchemy.pk_update_input(User, include=["id", "name"])
class UserUpdateWithPostsInput:
    posts: auto


@strawberry.type
class Mutation:
    update_user_with_posts: UserType = strawchemy.update_by_ids(UserUpdateWithPostsInput)
```

```graphql
mutation {
    updateUserWithPosts(data: { id: 1, name: "Alice", posts: { set: [{ id: 1 }] } }) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

## Adding to a relationship

`add` attaches existing posts to the collection without touching the rest of it:

```graphql
mutation {
    updateUserWithPosts(data: { id: 1, name: "Alice", posts: { add: [{ id: 2 }] } }) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

## Removing from a relationship

`remove` detaches posts from the collection, leaving the records themselves intact:

```graphql
mutation {
    updateUserWithPosts(data: { id: 1, name: "Alice", posts: { remove: [{ id: 2 }] } }) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

## Creating while updating

```graphql
mutation {
    updatePostWithAuthor(
        data: { id: 1, title: "Updated title", author: { create: { id: 6, name: "Frank", email: "frank@example.com" } } }
    ) {
        id
        title
        author {
            id
            name
        }
    }
}
```

`posts` accepts `create` the same way, adding new posts to the collection:

```graphql
mutation {
    updateUserWithPosts(data: { id: 1, name: "Alice", posts: { create: [{ id: 7, title: "New post", content: "..." }] } }) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

## Combining operations

An update can combine `add` and `create`:

```graphql
mutation {
    updateUserWithPosts(
        data: {
            id: 1
            name: "Alice"
            posts: { add: [{ id: 2 }], create: [{ id: 8, title: "Combined", content: "..." }] }
        }
    ) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

Combining `set` with `create`, `upsert`, `add` or `remove` on the same to-many field raises an error:

```graphql
mutation {
    updateUserWithPosts(
        data: { id: 1, name: "Alice", posts: { set: [{ id: 1 }], add: [{ id: 2 }] } } # [!code error]
    ) {
        id
        name
        posts {
            id
            title
        }
    }
}
```

```
You cannot use `set` with `create`, `upsert`, `add` or `remove` in a -to-many relation input
```
