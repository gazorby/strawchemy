# Mutations

Once a model maps to a type, your schema can create, update and delete records as well as query them. You build mutations the same way as queries: an input type from the model, then a field on a `Mutation` type.

## Declaring an input

These decorators build the input types a mutation reads its data from, plus a filter input for the mutations that take one:

```python
@strawchemy.create_input(Post, include=["title", "content", "views"])
class PostCreateInput: ...


@strawchemy.pk_update_input(Post, include=["id", "title"])
class PostUpdateInput: ...


@strawchemy.filter_update_input(Post, include=["title"])
class PostPartialInput: ...


@strawchemy.create_input(Post, include=["id", "title", "content", "views"])
class PostUpsertInput: ...


@strawchemy.upsert_update_fields(Post, include=["content", "views"])
class PostUpsertFields: ...


@strawchemy.upsert_conflict_fields(Post)
class PostConflictFields: ...


@strawchemy.filter(Post, include="all")
class PostFilter: ...
```

## Adding the fields

Each field pairs one of those inputs with a mutation method. For create, update by id and upsert, the return annotation decides whether a mutation acts on a single record or a batch — `PostType` for one, `list[PostType]` for many. Update by filter and delete always return a list:

```python
@strawberry.type
class Mutation:
    create_post: PostType = strawchemy.create(PostCreateInput)
    create_posts: list[PostType] = strawchemy.create(PostCreateInput)

    update_post: PostType = strawchemy.update_by_ids(PostUpdateInput)
    update_posts: list[PostType] = strawchemy.update_by_ids(PostUpdateInput)
    update_posts_filter: list[PostType] = strawchemy.update(PostPartialInput, PostFilter)

    delete_posts: list[PostType] = strawchemy.delete()
    delete_posts_filter: list[PostType] = strawchemy.delete(PostFilter)

    upsert_post: PostType = strawchemy.upsert(
        PostUpsertInput, update_fields=PostUpsertFields, conflict_fields=PostConflictFields
    )
    upsert_posts: list[PostType] = strawchemy.upsert(
        PostUpsertInput, update_fields=PostUpsertFields, conflict_fields=PostConflictFields
    )
```

## Building the schema

```python
schema = strawberry.Schema(query=Query, mutation=Mutation)
```

Each operation has its own page:

- [Create](/learn/mutations/create) — insert new records, singly or in batch.
- [Nested create](/learn/mutations/relationships-create) — insert records together with related records.
- [Update](/learn/mutations/update) — modify existing records by primary key or by filter.
- [Nested update](/learn/mutations/relationships-update) — modify related records alongside their parent.
- [Delete](/learn/mutations/delete) — remove records, all or matching a filter.
- [Upsert](/learn/mutations/upsert) — insert or update in a single operation.
- [Validation](/learn/mutations/validation) — validate mutation input before it reaches the database.
