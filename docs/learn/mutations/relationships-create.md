# Nested create

A relationship field declared `auto` on a create input gets its own operations for reaching across that relationship, instead of taking a plain scalar value.

## Linking existing records

`author: auto` on `PostCreateWithAuthorInput` lets `createPostWithAuthor` link the new post to an existing user by id, with `set`:

```python
from strawberry import auto


@strawchemy.create_input(Post, include=["title", "content"])
class PostCreateWithAuthorInput:
    author: auto


@strawberry.type
class Mutation:
    create_post_with_author: PostType = strawchemy.create(PostCreateWithAuthorInput)
```

```graphql
mutation {
    createPostWithAuthor(data: { title: "Hello", content: "...", author: { set: { id: 1 } } }) {
        id
        title
        author {
            id
            name
        }
    }
}
```

## Creating the related record

The same field accepts `create`, which writes the related user in the same mutation as the post:

```graphql
mutation {
    createPostWithAuthor(
        data: { title: "Hello", content: "...", author: { create: { id: 2, name: "Bob", email: "bob@example.com" } } }
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

`Post.id` and `User.id` are plain autoincrement columns with no Python-side default, so the nested `create` needs its own `id` — leaving it out fails:

```graphql
mutation {
    createPostWithAuthor(
        data: { title: "Hello", content: "...", author: { create: { name: "Bob", email: "bob@example.com" } } } # [!code error]
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

```
Field 'PostUserInput.id' of required type 'Int!' was not provided.
```

## Several related records

The same `auto` declaration works on a to-many field. `posts: auto` on `UserCreateWithPostsInput` accepts:

- `set` — link existing posts by id
- `add` — attach existing posts alongside any created here
- `create` — create new posts

```python
@strawchemy.create_input(User, include=["name", "email"])
class UserCreateWithPostsInput:
    posts: auto


@strawberry.type
class Mutation:
    create_user_with_posts: UserType = strawchemy.create(UserCreateWithPostsInput)
```

Each post created alongside the user needs an `id`, for the same reason as the to-one case above:

```graphql
mutation {
    createUserWithPosts(
        data: {
            name: "Carol"
            email: "carol@example.com"
            posts: { create: [{ id: 3, title: "Hello", content: "..." }, { id: 4, title: "GraphQL basics", content: "..." }] }
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

## Creating a whole tree

Nesting goes to any depth: creating a user can create its posts, and each of those posts can in turn create its tags, all in one mutation. Every created record still needs its own `id`:

```graphql
mutation {
    createUserWithPosts(
        data: {
            name: "Dave"
            email: "dave@example.com"
            posts: {
                create: [
                    {
                        id: 5
                        title: "Hello"
                        content: "..."
                        tags: { create: [{ id: 1, name: "intro" }] }
                    }
                ]
            }
        }
    ) {
        name
        posts {
            title
            tags {
                name
            }
        }
    }
}
```

## Empty relationships

`author` is optional on `Post`. To create a post without one, leave it out of `data` or pass `author: { set: null }`:

```graphql
mutation {
    createPostWithAuthor(data: { title: "Draft", content: "..." }) {
        id
        title
        author {
            id
        }
    }
}
```

```graphql
mutation {
    createPostWithAuthor(data: { title: "Draft", content: "...", author: { set: null } }) {
        id
        title
        author {
            id
        }
    }
}
```
