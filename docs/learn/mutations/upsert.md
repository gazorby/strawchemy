# Upsert

## Upserting a record

Three decorators build the pieces an upsert needs:

- the input data
- which fields can be updated on conflict
- which field detects a conflict

Together with `strawchemy.upsert`, they give you a mutation that inserts a new record, or updates
the matching one if a conflict is found:

```python
@strawchemy.create_input(Post, include=["id", "title", "content", "views"])
class PostUpsertInput: ...


@strawchemy.upsert_update_fields(Post, include=["content", "views"])
class PostUpsertFields: ...


@strawchemy.upsert_conflict_fields(Post)
class PostConflictFields: ...


@strawberry.type
class Mutation:
    upsert_post: PostType = strawchemy.upsert(
        PostUpsertInput, update_fields=PostUpsertFields, conflict_fields=PostConflictFields
    )
```

`conflictFields` can only name a column covered by a unique constraint — a primary key, or a column
declared with `UniqueConstraint`. `Post` has no unique columns of its own, so `id` is the only
usable conflict field here, and `PostUpsertInput` includes it so the caller can supply a value to
check.

```graphql
mutation {
    upsertPost(data: { id: 1, title: "Hello", content: "...", views: 0 }, conflictFields: id) {
        id
        title
        views
    }
}
```

Calling it again with the same `id` updates the existing record instead of creating a second one.
Leaving out `updateFields` updates every field present in `data`, including `title`, even though
`title` isn't one of `PostUpsertFields`' members:

```graphql
mutation {
    upsertPost(data: { id: 1, title: "Renamed", content: "Updated content", views: 10 }, conflictFields: id) {
        id
        title
        content
        views
    }
}
```

Conflict handling runs at the database level:

- **PostgreSQL** — `ON CONFLICT DO UPDATE`.
- **SQLite** — `ON CONFLICT DO UPDATE`.
- **MySQL** — `ON DUPLICATE KEY UPDATE`.

Naming a field with no unique constraint in `conflictFields` never reaches the mutation: `title`
was never added to the enum in the first place, since `Post.title` has no unique constraint —
`PostConflictFields` only has an `id` member. GraphQL rejects the request before execution:

```graphql
mutation {
    upsertPost(
        data: { id: 1, title: "Hello", content: "...", views: 0 }
        conflictFields: title # [!code error]
    ) {
        id
        title
    }
}
```

```
Value 'title' does not exist in 'PostConflictFields' enum.
```

## Upserting several

```python
@strawberry.type
class Mutation:
    upsert_post: PostType = strawchemy.upsert(
        PostUpsertInput, update_fields=PostUpsertFields, conflict_fields=PostConflictFields
    )
    upsert_posts: list[PostType] = strawchemy.upsert(  # [!code ++]
        PostUpsertInput,
        update_fields=PostUpsertFields,
        conflict_fields=PostConflictFields,  # [!code ++]
    )  # [!code ++]
```

`upsertPosts` takes `data` as a list — each item is checked against `conflictFields` independently:

```graphql
mutation {
    upsertPosts(
        data: [
            { id: 2, title: "Second post", content: "...", views: 0 }
            { id: 3, title: "Third post", content: "...", views: 0 }
        ]
        conflictFields: id
    ) {
        id
        title
    }
}
```

## Update fields

Passing `updateFields` narrows a conflict update down to the fields you list, leaving the rest of
the existing record untouched:

```graphql
mutation {
    upsertPost(
        data: { id: 1, title: "Renamed", content: "Updated content", views: 10 }
        conflictFields: id
        updateFields: [content, views]
    ) {
        id
        title
        content
        views
    }
}
```

`title` is part of `data` but not of `updateFields`, so it keeps its stored value instead of
becoming `"Renamed"`. Only fields declared on `PostUpsertFields` — `content` and `views` here — can
appear in `updateFields`.

## Upserting related records

Upsert also works inside a relationship input — `posts: auto` includes an `upsert` option
alongside `set`, `add`, `remove` and `create`, so a parent mutation can upsert its related records
in the same call:

```python
from strawberry import auto


@strawchemy.pk_update_input(User, include=["id", "name"])
class UserUpsertPostsInput:
    posts: auto


@strawberry.type
class Mutation:
    upsert_user_posts: UserType = strawchemy.update_by_ids(UserUpsertPostsInput)
```

```graphql
mutation {
    upsertUserPosts(
        data: {
            id: 1
            name: "Alice"
            posts: {
                upsert: { create: [{ id: 10, title: "Upserted post", content: "..." }], conflictFields: id }
            }
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
