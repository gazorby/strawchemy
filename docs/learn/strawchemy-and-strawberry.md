# Strawchemy and Strawberry

Strawchemy is built on top of Strawberry, not beside it. It reads your SQLAlchemy models and
produces ordinary Strawberry types, inputs, and fields. The schema, the server integration, the
extensions, and the permissions all stay Strawberry's. You can therefore adopt it in an existing
Strawberry codebase without a rewrite, one field at a time.

## Strawberry compatibility

A Strawchemy type is a Strawberry type: your own `@strawberry.type` classes sit beside the
generated ones, and so do plain resolvers that never touch a mapped model. `Query` and `Mutation`
are ordinary Strawberry classes too, and the fields Strawchemy builds sit beside your own.

`strawchemy.field()` and the mutation factories accept the `strawberry.field` arguments
`description`, `deprecation_reason`, `directives`, `permission_classes`, and `extensions`, and pass
them to the generated field unchanged:

```python
posts: list[PostType] = strawchemy.field(
    filter_input=PostFilter,
    description="Published posts",
    deprecation_reason="use postsConnection instead",
)
```

Both show up on the generated field exactly as passed:

```graphql
type Query {
  """Published posts"""
  posts(filter: PostFilter = null): [PostType!]! @deprecated(reason: "use postsConnection instead")
}
```

Since the result is an ordinary `strawberry.Schema`, any Strawberry server integration serves it.
The quickstart app plugs it into Litestar by passing `schema` to `make_graphql_controller`.

## Migrating an existing schema

Strawchemy starts resolving fields while the rest of your schema stays as it is. A typical
migration takes four steps:

1. **Give it the session you already have.** By default Strawchemy reads `session` from
   `info.context`, then from `info.context.request`; a context that already carries one needs no
   setup. Otherwise, set [`session_getter`](/learn/configuration#session-getter) on
   `StrawchemyConfig`. An async session also needs `repository_type`, as
   [async sessions](/learn/async) shows.
2. **Map one model and add one field.** The new field joins the hand-written ones on the same
   `Query`:

   ```python
   strawchemy = Strawchemy(StrawchemyConfig("postgresql"))


   @strawchemy.type(Post, include="all")
   class PostType: ...


   @strawberry.type
   class Query:
       @strawberry.field
       def users(self, info: strawberry.Info) -> list[UserType]: ...  # existing resolver, untouched

       posts: list[PostType] = strawchemy.field()
   ```

3. **Replace hand-written resolvers one at a time.** For a mapped model, one declaration replaces
   the resolver, the session-fetching code, and the arguments it reads:

   ```python
   users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
   ```

   This field accepts `filter`, `orderBy`, `limit`, and `offset`. [Filtering](/learn/filtering),
   [ordering](/learn/ordering), and [pagination](/learn/pagination) describe these arguments;
   [architecture](/learn/architecture#generated-fields) describes the generated resolver.
   [Mutation](/learn/mutations/) fields work the same way, with generated input types in place of
   hand-written ones.
4. **Keep the resolvers no generated field can replace.** Decorate such a resolver with
   `@strawchemy.field` and fetch its data through a repository; Strawchemy still builds the query.
   [Custom resolvers](/learn/resolvers) shows how.

Each step leaves a working schema; you can stop after any of them.

## Accepted field types

A field Strawchemy resolves itself builds its query from a Strawchemy type. On a
`strawchemy.field()` or mutation field without a resolver of its own, the first member of the
annotation that isn't an error type must be one; plain Strawberry types may follow it in a union:

```python
@strawberry.type
class Query:
    user_or_plain: UserType | Plain = strawchemy.field()
    plain: list[Plain] = strawchemy.field()  # [!code error]
```

```
strawchemy.exceptions.StrawchemyFieldError: The `plain` field has no resolver but its type `Plain` is not a strawchemy type.
```

`Plain | UserType` fails the same way, and an annotation made only of error types, such as
`list[ValidationErrorType]`, raises "…its type only contains error types." A method decorated with
`@strawchemy.field` may return any type — a plain Strawberry type, a scalar, error types alone —
but `default_order_by` still needs a Strawchemy type, and `root_aggregations` an
[aggregation type](/learn/aggregations#aggregating-a-result-set), resolver or not.

These checks run when the class holding the field is decorated, or at `strawberry.Schema(...)` for
an annotation naming a type declared further down the module, where Strawberry wraps the
`StrawchemyFieldError` in a `TypeError`. Under `from __future__ import annotations`, a name
Strawchemy has registered takes precedence over a module-level name when the annotation resolves.

## Replacing dataloaders

Dataloaders batch a relationship across the N+1 resolver calls a naive implementation would make.
Strawchemy leaves a dataloader nothing to batch: it compiles the whole selection set into one SQL
statement before running it, and a nested `posts` selection becomes a join in that statement. A
three-level selection plus a relationship aggregate still compiles to one statement:

```graphql
{
    users {
        name
        postsAggregate {
            count
        }
        posts {
            title
            tags {
                name
            }
        }
    }
}
```

[Architecture](/learn/architecture) describes the execution model behind this. Your existing
dataloaders keep serving the fields Strawchemy leaves to hand-written resolvers.

## Generating relationship inputs

`strawberry.auto` changes meaning on a Strawchemy input. In plain Strawberry, it means "infer
this field's type." On a Strawchemy input it means "generate the relationship input for this
field," built from up to four operations — a to-many field gets all four, a to-one field all but
`add`:

- `set` — link an existing related record by id
- `add` — attach an existing related record alongside any created here (to-many only)
- `create` — create a new related record
- `upsert` — create a new related record, or update the existing one it conflicts with

```python
@strawchemy.create_input(Post, include=["title", "content"])
class PostCreateWithAuthorInput:
    author: auto
```

See [create mutations with relationships](/learn/mutations/relationships-create) for what each
operation accepts.

## Adding computed fields

A Strawchemy type can also hold fields you write. Add a `ModelInstance` attribute to reach the
underlying SQLAlchemy instance, then expose a computed field as a method decorated with
`@strawchemy.field`:

```python
@strawchemy.type(User, include="all")
class UserType:
    instance: ModelInstance[User]

    @strawchemy.field
    def post_count(self) -> int:
        return len(self.instance.posts)
```

`post_count` reads `instance.posts`, but the generated query never loads relationships onto the
instance, even those the client selects. A `QueryHook` adds that load to the statement Strawchemy
already builds:

```python
@strawchemy.field(query_hook=QueryHook(load=[User.posts]))
def post_count(self) -> int:
    return len(self.instance.posts)
```

See [mapping models](/learn/mapping-models) for `ModelInstance` and computed fields, and
[loading extra data](/learn/query-hooks#loading-extra-data) for the rest of what `load` can do.
