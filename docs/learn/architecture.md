# Architecture

Five pieces make up a Strawchemy schema: a mapper holding the configuration, the types it generates from a SQLAlchemy model, the fields that expose those types, the repository that runs the query behind a field, and the transpiler that turns a nested selection into one SQL statement.

## The mapper

`Strawchemy` is the entry point. It holds the `StrawchemyConfig` that every decorator and field below it inherits — the SQL dialect, the repository class, the defaults for field selection, pagination and ordering — and it is the registry of generated types, so it reuses a type it has already built rather than building it a second time.

```python
strawchemy = Strawchemy(StrawchemyConfig("sqlite"))
```

[Configuration](/learn/configuration) lists the mapper's options.

## Mapped types and inputs

One model becomes several GraphQL types, one per purpose, each produced by its own decorator reading the same model:

- `@strawchemy.type` — the output type a field returns
- `@strawchemy.filter` — the type behind a field's `filter` argument
- `@strawchemy.order` — the type behind `orderBy`
- `@strawchemy.distinct_on` — the enum behind `distinctOn`
- `@strawchemy.aggregate` — the type a root aggregation field returns
- `@strawchemy.create_input`, `@strawchemy.pk_update_input`, `@strawchemy.filter_update_input` — the mutation inputs

A decorator reads the model's columns and its relationships, and follows those relationships: generating a type also generates the types for the models reachable from it, so a related model needs no mapping of its own.

[Mapping models](/learn/mapping-models) covers the output and filter side, [Mutations](/learn/mutations/) the input side.

## Generated fields

`strawchemy.field` puts a mapped type on a Strawberry type and generates the resolver behind it, so the field is declared rather than written. What you pass the field decides two things at once: the arguments it exposes on the schema, and the query the resolver builds. A filter type, an order-by type, pagination or a distinct-on enum each adds an argument and the clause behind it; a filter statement or a query hook changes the query with nothing added to the schema.

Decorating a method of your own with `strawchemy.field` keeps all of that and lets the body drive the repository itself, so custom logic sits around Strawchemy's data access rather than replacing it.

[Custom resolvers](/learn/resolvers) covers writing your own, [Query hooks](/learn/query-hooks) reaching into the statement, [Pagination](/learn/pagination) and [Ordering](/learn/ordering) the arguments that carry their names, and [Queries](/learn/queries) putting a field together end to end.

## Repositories and the session

A generated resolver does no data access itself. It hands the GraphQL selection, the field's arguments and any hooks to a repository — `StrawchemySyncRepository` or `StrawchemyAsyncRepository`, whichever the mapper's `repository_type` names. The repository reads the selection into a tree of query nodes, asks the transpiler for the statement, executes it, and builds the Strawberry objects from the rows.

To execute it, the repository needs a SQLAlchemy session, which it gets by calling `session_getter` with the resolver's `Info`. That call is the seam between Strawchemy and the application's own session management: rather than opening a connection of its own, Strawchemy runs against the session the application put on the GraphQL context.

[Async sessions](/learn/async) covers choosing between the two repositories; pointing the getter at your own session is a [Configuration](/learn/configuration) option.

## The transpiler

The transpiler compiles the field's whole selection into one statement before the repository runs it. A nested selection is therefore one round trip, not one per level, and relationship fields need no dataloader. The one exception is a relationship a [query hook](/learn/query-hooks) loads, which adds one `SELECT … IN` query of its own.

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

Every argument in a GraphQL query applies to one node of the tree, while SQL clauses apply to the whole joined table. The transpiler places each part of the tree where its arguments keep their meaning:

- A relationship with no arguments of its own becomes a plain join.
- A relationship with its own ordering, pagination or `distinctOn` becomes a lateral join on PostgreSQL and a ranked CTE on SQLite and MySQL.
- A filter on a to-many relationship becomes an `EXISTS` subquery; a filter on a to-one relationship becomes an inner join that the selection reuses.
- A paginated root becomes a subquery, so `limit` counts root rows rather than joined ones.
- A relationship aggregation becomes a grouped join that returns one row per parent, computed alongside the fields around it; see [Aggregations](/learn/aggregations).
- Several aliases of one relationship share a single read.

The statement never reads the same data twice: a filter, an ordering and a selection that need the same join or aggregate get the same one.

[Transpiler internals](/learn/transpiler) explains how the transpiler cuts the tree into SQL scopes, plans each one, and rebuilds the tree from the rows.
