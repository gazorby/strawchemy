# Strawchemy and Strawberry

Strawchemy generates GraphQL types, resolvers and inputs from SQLAlchemy models, but the schema
underneath is Strawberry's own. This page marks what carries over unchanged, what Strawchemy
takes off your hands, two Strawberry patterns that don't apply to a mapped model, and the two
places a generated type and a hand-written field share one class.

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

`post_count` needs `instance.posts` loaded, which the generated query only does when something
else in the selection also asked for `posts`. A `QueryHook` guarantees it regardless of what the
client selected, by adding the load to the statement Strawchemy is already building:

```python
@strawchemy.field(query_hook=QueryHook(load=[User.posts]))
def post_count(self) -> int:
    return len(self.instance.posts)
```

See [mapping models](/learn/mapping-models) for `ModelInstance` and computed fields, and
[query hooks](/learn/query-hooks) for the rest of what `QueryHook` can do.
