# Configuration

Configuration is made by passing a `StrawchemyConfig` to the `Strawchemy` instance.

## Configuration Options

| Option                      | Type                                                        | Default                    | Description                                                                                                                                                                                |
|-----------------------------|-------------------------------------------------------------|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dialect`                   | `SupportedDialect`                                          |                            | Database dialect to use. Supported dialects are "postgresql", "mysql", "sqlite".                                                                                                           |
| `session_getter`            | `Callable[[Info], Session]`                                 | `default_session_getter`   | Function to retrieve SQLAlchemy session from strawberry `Info` object. By default, it retrieves the session from `info.context.session`.                                                   |
| `auto_snake_case`           | `bool`                                                      | `True`                     | Automatically convert snake cased names to camel case in GraphQL schema.                                                                                                                   |
| `repository_type`           | `type[Repository] \| StrawchemySyncRepository`              | `StrawchemySyncRepository` | Repository class to use for auto resolvers.                                                                                                                                                |
| `filter_overrides`          | `OrderedDict[tuple[type, ...], type[SQLAlchemyFilterBase]]` | `None`                     | Override default filters with custom filters. This allows you to provide custom filter implementations for specific column types.                                                          |
| `execution_options`         | `dict[str, Any]`                                            | `None`                     | SQLAlchemy execution options for repository operations. These options are passed to the SQLAlchemy `execution_options()` method.                                                           |
| `default_id_field_name`     | `str`                                                       | `"id"`                     | Name for primary key fields arguments on primary key resolvers.                                                                                                                            |
| `deterministic_ordering`    | `bool`                                                      | `True`                     | Force deterministic ordering for list resolvers.                                                                                                                                           |
| `strict`                    | `bool`                                                      | `True`                     | When `True`, a column whose Python type hint has no GraphQL mapping (arbitrary class, Pydantic model without a Strawberry wrapper, `TypedDict`, opaque JSONB type) fails the schema build. |
| `pagination`                | `Literal["all"] \| None`                                    | `None`                     | Enable/disable pagination on list resolvers by default. Set to `"all"` to enable pagination on all list fields.                                                                            |
| `order_by`                  | `Literal["all"] \| None`                                    | `None`                     | Enable/disable order by on list resolvers by default. Set to `"all"` to enable ordering on all list fields.                                                                                |
| `pagination_default_limit`  | `int`                                                       | `100`                      | Default pagination limit when `pagination=True`.                                                                                                                                           |
| `pagination_default_offset` | `int`                                                       | `0`                        | Default pagination offset when `pagination=True`.                                                                                                                                          |

## Example

```python
from strawchemy import Strawchemy, StrawchemyConfig


# Custom session getter function
def get_session_from_context(info):
    return info.context.db_session


# Initialize with custom configuration
strawchemy = Strawchemy(
    StrawchemyConfig(
        "postgresql",
        session_getter=get_session_from_context,
        auto_snake_case=True,
        pagination="all",
        pagination_default_limit=50,
        pagination_default_offset=0,
        order_by="all",
        default_id_field_name="pk",
    )
)
```

Every option, with its type and default, is tabulated in the [configuration reference](/reference/config).
