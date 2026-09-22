# Queries

A mapped type plus a field on `Query` is all a read API needs. The field's arguments come from what you pass to `strawchemy.field()`.

## Declaring the types

The output type and the two inputs a query field takes. `UserAggregationType` comes from `@strawchemy.aggregate`, declared here so the third field below resolves:

```python
@strawchemy.type(User, include="all", override=True)
class UserType: ...


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.order(User, include="all")
class UserOrderBy: ...


@strawchemy.aggregate(User, include="all")
class UserAggregationType: ...
```

## Adding the fields

The return annotation decides the shape, exactly as it does for mutations: a list annotation gives a list field, a single annotation gives a get-by-id field whose `id` argument is generated (the name comes from `StrawchemyConfig.default_id_field_name`, `"id"` unless changed).

```python
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy)
    user: UserType = strawchemy.field()
    users_aggregate: UserAggregationType = strawchemy.field(root_aggregations=True)
```

Each argument to `strawchemy.field()` adds its own piece of the field:

- `filter_input` — adds a `filter` argument. [Filtering](/learn/filtering)
- `order_by_input` — adds an `orderBy` argument. [Ordering](/learn/ordering)
- `pagination` — adds `limit` and `offset`. [Pagination](/learn/pagination)
- `distinct_on` — adds a `distinctOn` argument, which restricts results to the first row for each distinct value of the given fields.
- `root_aggregations` — switches the field into aggregate mode. [Aggregations](/learn/aggregations)

## Building the schema

```python
schema = strawberry.Schema(query=Query)
```

- [Filtering](/learn/filtering) — narrow a list down with a `filter` argument.
- [Ordering](/learn/ordering) — sort a list with an `orderBy` argument.
- [Pagination](/learn/pagination) — page through a list with `limit` and `offset`.
- [Aggregations](/learn/aggregations) — count and summarize rows, per relationship or at the root.
- [Custom resolvers](/learn/resolvers) — write a resolver method backed by the same repository.
- [Query hooks](/learn/query-hooks) — reach into the statement Strawchemy builds before it runs.
