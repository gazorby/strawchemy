# Configuration

Pass options as a `StrawchemyConfig` to the `Strawchemy` instance; they apply to every type and field the mapper generates. A repository you build yourself in a [custom resolver](/learn/resolvers) doesn't read them: pass `session_getter`, `deterministic_ordering` or `execution_options` to its constructor.

## Configuration options

| Option                      | Type                                                         | Default                    | Description                                                                                                                                                                                |
|-----------------------------|---------------------------------------------------------------|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dialect`                   | `SupportedDialect`                                            |                            | Database dialect: "postgresql", "mysql" or "sqlite".                                                                                                           |
| `session_getter`            | `Callable[[Info], Session \| AsyncSession]`                    | `default_session_getter`   | Function that retrieves the SQLAlchemy session from the strawberry `Info` object. The default reads `session` from `info.context` (attribute or key), then from `info.context.request`.            |
| `auto_snake_case`           | `bool`                                                         | `True`                     | Convert snake case names to camel case in the GraphQL schema.                                                                                                                   |
| `repository_type`           | `type[StrawchemySyncRepository \| StrawchemyAsyncRepository]` | `StrawchemySyncRepository` | Repository class to use for auto resolvers.                                                                                                                                                |
| `filter_overrides`          | `OrderedDict[tuple[type, ...], type[GraphQLComparison]]`      | `None`                     | Replace the default filters for specific column types with custom filter implementations.                                                          |
| `execution_options`         | `dict[str, Any]`                                               | `None`                     | SQLAlchemy execution options for repository operations, passed to SQLAlchemy's `execution_options()` method.                                                           |
| `default_id_field_name`     | `str`                                                          | `"id"`                     | Name of the primary key argument on primary key resolvers.                                                                                                                               |
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

The [configuration reference](/reference/config) lists every option with its type and default.
