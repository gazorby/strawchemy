# Custom resolvers

When a generated field cannot express a query, write the resolver yourself and keep Strawchemy's data access by calling a repository from it.

## Fetching one record

Called as a function, `strawchemy.field()` builds a repository-backed resolver for you. Decorate your own method with `@strawchemy.field` to build that repository yourself and add your own logic around it — a lookup by title, say, which `strawchemy.field()` alone has no argument for:

```python
from sqlalchemy import select
from strawchemy import StrawchemySyncRepository


@strawberry.type
class Query:
    @strawchemy.field
    def get_post_by_title(self, info: strawberry.Info, title: str) -> PostType | None:
        repo = StrawchemySyncRepository(PostType, info, filter_statement=select(Post).where(Post.title == title))
        return repo.get_one_or_none().graphql_type_or_none()
```

`filter_statement` narrows the query before Strawchemy's own filtering, ordering and field-selection logic runs on top of it. A statement that only adds `WHERE` clauses to `select(Post)` has them copied into the query; any other statement is joined on the primary key, so its own `ORDER BY` doesn't order the result. The repository takes none of the field's arguments or the mapper's configuration: pass `query_hook`, `execution_options` or `deterministic_ordering` to it when you need them. `get_one_or_none()` runs it and returns a `GraphQLResult`; `graphql_type_or_none()` converts that into `PostType | None`.

Fetching by primary key needs no `filter_statement`: pass the key as a keyword argument to `get_by_id()`:

```python
@strawchemy.field
def get_post_by_id(self, info: strawberry.Info, id: int) -> PostType:
    repo = StrawchemySyncRepository(PostType, info)
    return repo.get_by_id(id=id).graphql_type()
```

`get_by_id()` takes the primary key's field name and value as keyword arguments — here `id`, matching `Post.id`. `graphql_type()` is the non-optional counterpart to `graphql_type_or_none()`: it raises instead of returning `None` when there's no match.

## Returning a list

```python
@strawchemy.field
def published_posts(self, info: strawberry.Info) -> list[PostType]:
    repo = StrawchemySyncRepository(PostType, info, filter_statement=select(Post).where(Post.published_at.is_not(None)))
    return repo.list().graphql_list()
```

The repository has four methods for fetching data, each paired with its own conversion call:

- `get_one()`, `get_one_or_none()` — return at most one result, and raise `MultipleResultsFound` if several rows match; `graphql_type()` then raises `QueryResultError` on no match, while `graphql_type_or_none()` returns `None`
- `get_by_id()` — returns a single result filtered on primary key
- `list()` — returns every matching result

`instance` and `instances` on the returned `GraphQLResult` give the model instances instead. Relationships the GraphQL query selected are not set on them: declare the ones your code reads in [`QueryHook(load=...)`](/learn/query-hooks).

See [async sessions](/learn/async) for the same resolvers written against `StrawchemyAsyncRepository`.

See [query hooks](/learn/query-hooks) for constraining every query against a type, and for loading data a custom field needs.
