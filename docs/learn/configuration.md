# Configuration

Options are passed as a `StrawchemyConfig` to the `Strawchemy` instance, and apply to every type and field the mapper generates.

## Configuration options

| Option                      | Type                                                         | Default                    | Description                                                                                                                                                                                |
|-----------------------------|---------------------------------------------------------------|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dialect`                   | `SupportedDialect`                                            |                            | Database dialect to use. Supported dialects are "postgresql", "mysql", "sqlite".                                                                                                           |
| `session_getter`            | `Callable[[Info], Session]`                                    | `default_session_getter`   | Function to retrieve SQLAlchemy session from strawberry `Info` object. By default, it retrieves the session from `info.context.session`.                                                   |
| `auto_snake_case`           | `bool`                                                         | `True`                     | Automatically convert snake cased names to camel case in GraphQL schema.                                                                                                                   |
| `repository_type`           | `type[StrawchemySyncRepository \| StrawchemyAsyncRepository]` | `StrawchemySyncRepository` | Repository class to use for auto resolvers.                                                                                                                                                |
| `filter_overrides`          | `OrderedDict[tuple[type, ...], type[GraphQLComparison]]`      | `None`                     | Override default filters with custom filters. This allows you to provide custom filter implementations for specific column types.                                                          |
| `execution_options`         | `dict[str, Any]`                                               | `None`                     | SQLAlchemy execution options for repository operations. These options are passed to the SQLAlchemy `execution_options()` method.                                                           |
| `default_id_field_name`     | `str`                                                          | `"id"`                     | Name for primary key fields arguments on primary key resolvers.                                                                                                                            |
| `deterministic_ordering`    | `bool`                                                         | `True`                     | Append the primary key, ascending, to any list query with no explicit `orderBy`, so paginated results return in a stable order across pages.                                              |
| `strict`                    | `bool`                                                         | `True`                     | When `True`, a column whose Python type hint has no GraphQL mapping (arbitrary class, Pydantic model without a Strawberry wrapper, `TypedDict`, opaque JSONB type) fails the schema build. |
| `auto_is_type_of`           | `bool`                                                          | `True`                     | Auto-generate `is_type_of` (an `isinstance` check against the model) on mapped types, so they work as GraphQL union/interface members with no extra code.                                  |
| `include`                   | `FieldSpec`                                                    | `"all"`                    | Fields included by default across every mapped type, unless a decorator overrides it with its own `include`.                                                                              |
| `exclude`                   | `FieldSpec \| None`                                            | `None`                     | Fields excluded by default across every mapped type, unless a decorator overrides it with its own `exclude`.                                                                               |
| `pagination`                | `FieldSpec \| None`                                            | `None`                     | Enable/disable pagination on list resolvers by default. Set to `"all"` to enable pagination on all list fields.                                                                            |
| `order_by`                  | `FieldSpec \| None`                                            | `None`                     | Enable/disable order by on list resolvers by default. Set to `"all"` to enable ordering on all list fields.                                                                                |
| `distinct_on`               | `FieldSpec \| None`                                            | `None`                     | Enable/disable a `distinctOn` argument on list resolvers by default. Set to `"all"` to enable it on all list fields; native on PostgreSQL, emulated elsewhere.                             |
| `pagination_default_limit`  | `int`                                                          | `100`                      | Default pagination limit when `pagination=True`.                                                                                                                                           |
| `pagination_default_offset` | `int`                                                          | `0`                        | Default pagination offset when `pagination=True`.                                                                                                                                          |

## Session getter

```python
from strawchemy import Strawchemy, StrawchemyConfig


def get_session_from_context(info):
    return info.context.db_session


strawchemy = Strawchemy(
    StrawchemyConfig(
        "postgresql",
        session_getter=get_session_from_context,
    )
)
```

Every option, with its type and default, is tabulated in the [configuration reference](/reference/config).
