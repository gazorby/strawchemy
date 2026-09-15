# Architecture

A Strawchemy schema is put together by five pieces: a mapper holding the configuration, the types it generates from a SQLAlchemy model, the fields that expose those types, the repository that runs the query behind a field, and the execution model that turns a nested selection into one SQL statement.

## The mapper

`Strawchemy` is the entry point. It holds the `StrawchemyConfig` that every decorator and field below it inherits — the SQL dialect, the repository class, the defaults for field selection, pagination and ordering — and it is the registry the generated types are recorded in, so a type it has already built is reused rather than built a second time.

```python
strawchemy = Strawchemy(StrawchemyConfig("sqlite"))
```

What the mapper can be configured with is listed under [Configuration](/learn/configuration).

## Mapped types and inputs

One model becomes several GraphQL types, one per purpose, each produced by its own decorator reading the same model:

- `@strawchemy.type` — the output type a field returns
- `@strawchemy.filter` — the type behind a field's `filter` argument
- `@strawchemy.order` — the type behind `orderBy`
- `@strawchemy.create_input`, `@strawchemy.pk_update_input`, `@strawchemy.filter_update_input` — the mutation inputs

A decorator reads the model's columns and its relationships, and follows those relationships: generating a type also generates the types for the models reachable from it, so a related model needs no mapping of its own.

[Mapping models](/learn/mapping-models) covers the output and filter side, [Mutations](/learn/mutations/) the input side.

## Generated fields

`strawchemy.field` puts a mapped type on a Strawberry type and generates the resolver behind it, so the field is declared rather than written. What the field is handed decides two things at once: the arguments it exposes on the schema, and the query the resolver builds. A filter type, an order-by type, pagination or a distinct-on enum each add an argument and the clause behind it; a filter statement or a query hook change the query with nothing added to the schema.

Decorating a method of your own with `strawchemy.field` keeps all of that and lets the body drive the repository itself, so custom logic sits around Strawchemy's data access rather than replacing it.

[Custom resolvers](/learn/resolvers) covers writing your own, [Query hooks](/learn/query-hooks) reaching into the statement, [Pagination](/learn/pagination) and [Ordering](/learn/ordering) the arguments that carry their names, and [Queries](/learn/queries) putting a field together end to end.

## Repositories and the session

A generated resolver does no data access itself. It hands the GraphQL selection, the field's arguments and any hooks to a repository — `StrawchemySyncRepository` or `StrawchemyAsyncRepository`, whichever the mapper's `repository_type` names — and the repository is what builds the statement and executes it.

To execute it needs a SQLAlchemy session, which it gets by calling `session_getter` with the resolver's `Info`. That call is the seam between Strawchemy and the application's own session management: rather than opening a connection of its own, Strawchemy runs against the session the application put on the GraphQL context.

[Async sessions](/learn/async) covers choosing between the two repositories; pointing the getter at your own session is a [Configuration](/learn/configuration) option.

## Execution model

The repository compiles the whole selection set into a single statement before running it, nesting relationships as lateral or CTE joins. A nested selection is therefore one round trip, not one per level, and relationship fields need no dataloader — there is never a second query to batch.

```graphql
{
    users {
        name
        posts {
            title
        }
    }
}
```

Aggregations belong to that same statement, computed alongside the fields around them rather than by a query of their own; see [Aggregations](/learn/aggregations).
