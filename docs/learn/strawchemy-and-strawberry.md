# Strawchemy and Strawberry

Strawchemy generates GraphQL types, resolvers and inputs from SQLAlchemy models, but the schema
underneath is Strawberry's own. This page marks what carries over unchanged, what Strawchemy
takes off your hands and the types it needs to do so, two Strawberry patterns that don't apply to
a mapped model, and the two places a generated type and a hand-written field share one class.

## What still works

A Strawchemy type is a Strawberry type: nothing stops you from adding your own `@strawberry.type`
classes beside the generated ones, or a plain resolver that never touches a mapped model. `Query`
and `Mutation` are ordinary Strawberry classes too — fields Strawchemy builds sit next to fields
you wrote yourself.

`strawchemy.field()` and the mutation factories also forward `strawberry.field` arguments you
already know onto the generated field — `description`, `deprecation_reason`, `directives`,
`permission_classes` and `extensions` reach it unchanged:

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

And because the result is an ordinary `strawberry.Schema`, any Strawberry server integration works
without change — the quickstart app wires it into Litestar with nothing beyond passing `schema` to
`make_graphql_controller`.

## What Strawchemy replaces

For a mapped model, Strawchemy takes over the parts that would otherwise be near-identical
boilerplate on every type: the resolver, the input types mutations read data from, and the
filter/order-by/pagination arguments those resolvers accept.

```python
users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
```

One declaration is the resolver, the `filter`/`orderBy`/`limit`/`offset` arguments, and the
session-fetching code all at once. See [architecture](/learn/architecture#generated-fields) for
what the generated resolver does, and [filtering](/learn/filtering), [ordering](/learn/ordering) and
[pagination](/learn/pagination) for the arguments it adds. Mutations get the same treatment —
[mutations](/learn/mutations/) covers the input types Strawchemy generates in place of hand-written
ones.

## Which types a field accepts

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

## What doesn't apply

Dataloaders batch a relationship across the N+1 resolver calls a naive implementation would make.
Strawchemy never resolves a relationship with a call of its own to batch: it compiles the whole
selection set into one SQL statement before running it, so a nested `posts` selection is a join in
that same statement. A three-level selection plus a relationship aggregate still compiles to one
statement:

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

There's nothing here to batch — see [architecture](/learn/architecture) for the execution model
that makes it so.

`strawberry.auto` also changes meaning on a Strawchemy input. In plain Strawberry it means "infer
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

## Where the two meet

A Strawchemy type isn't limited to generated fields. Add a `ModelInstance` attribute to reach the
underlying SQLAlchemy instance, then write a plain method decorated with `@strawchemy.field` to
expose it as a computed field beside the generated ones:

```python
@strawchemy.type(User, include="all")
class UserType:
    instance: ModelInstance[User]

    @strawchemy.field
    def post_count(self) -> int:
        return len(self.instance.posts)
```

`post_count` needs `instance.posts` loaded, which the generated query never does: relationships
the client selects are not set on the instance. A `QueryHook` loads it, by adding the load to the
statement Strawchemy is already building:

```python
@strawchemy.field(query_hook=QueryHook(load=[User.posts]))
def post_count(self) -> int:
    return len(self.instance.posts)
```

See [mapping models](/learn/mapping-models) for `ModelInstance` and computed fields, and
[loading extra data](/learn/query-hooks#loading-extra-data) for the rest of what `load` can do.
