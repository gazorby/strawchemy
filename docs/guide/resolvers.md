# Resolver Generation

Strawchemy automatically generates resolvers for your GraphQL fields. You can use the `strawchemy.field()` function to
generate fields that query your database

<details>
<summary>Resolvers example</summary>

```python
@strawberry.type
class Query:
    # Simple field that returns a list of users
    users: list[UserType] = strawchemy.field()
    # Field with filtering, ordering, and pagination
    filtered_users: list[UserType] = strawchemy.field(
        filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True
    )
    # Field that returns a single user by ID
    user: UserType = strawchemy.field()
```

</details>

While Strawchemy automatically generates resolvers for most use cases, you can also create custom resolvers for more
complex scenarios. There are two main approaches to creating custom resolvers:

## Using Repository Directly

When using `strawchemy.field()` as a function, strawchemy creates a resolver that delegates data fetching to the
`StrawchemySyncRepository` or `StrawchemyAsyncRepository` classes depending on the SQLAlchemy session type.
You can create custom resolvers by using the `@strawchemy.field` as a decorator and working directly with the
repository:

<details>
<summary>Custom resolvers using repository</summary>

```python
from sqlalchemy import select, true
from strawchemy import StrawchemySyncRepository


@strawberry.type
class Query:
    @strawchemy.field
    def red_color(self, info: strawberry.Info) -> ColorType:
        # Create a strawberry with a predefined filter
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == "Red"))
        # Return a single result (will raise an exception if not found)
        return repo.get_one().graphql_type()

    @strawchemy.field
    def get_color_by_name(self, info: strawberry.Info, color: str) -> ColorType | None:
        # Create a strawberry with a custom filter statement
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        # Return a single result or None if not found
        return repo.get_one_or_none().graphql_type_or_none()

    @strawchemy.field
    def get_color_by_id(self, info: strawberry.Info, id: str) -> ColorType | None:
        repo = StrawchemySyncRepository(ColorType, info)
        # Return a single result or None if not found
        return repo.get_by_id(id=id).graphql_type_or_none()

    @strawchemy.field
    def public_colors(self, info: strawberry.Info) -> ColorType:
        repo = StrawchemySyncRepository(ColorType, info, filter_statement=select(Color).where(Color.public.is_(true())))
        # Return a list of results
        return repo.list().graphql_list()
```

For async resolvers, use `StrawchemyAsyncRepository` which is the async variant of `StrawchemySyncRepository`:

```python
from strawchemy import StrawchemyAsyncRepository


@strawberry.type
class Query:
    @strawchemy.field
    async def get_color(self, info: strawberry.Info, color: str) -> ColorType | None:
        repo = StrawchemyAsyncRepository(ColorType, info, filter_statement=select(Color).where(Color.name == color))
        return (await repo.get_one_or_none()).graphql_type_or_none()
```

The repository provides several methods for fetching data:

- `get_one()`: Returns a single result, raises an exception if not found
- `get_one_or_none()`: Returns a single result or None if not found
- `get_by_id()`: Returns a single result filtered on primary key
- `list()`: Returns a list of results

</details>

## Query Hooks

Strawchemy provides query hooks that allow you to customize query behavior. Query hooks give you fine-grained control
over how SQL queries are constructed and executed.

<details>
<summary>Using query hooks</summary>

The `QueryHook` base class provides several methods that you can override to customize query behavior:

### Modifying the statement

You can subclass `QueryHook` and override the `apply_hook` method apply changes to the statement. By default, it returns
it unchanged. This method is only for filtering or ordering customizations, if you want to explicitly load columns or
relationships, use the `load` parameter instead.

```python
from strawchemy import ModelInstance, QueryHook
from sqlalchemy import Select, select
from sqlalchemy.orm.util import AliasedClass


# Define a model and type
class Fruit(Base):
    __tablename__ = "fruit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    adjectives: Mapped[list[str]] = mapped_column(ARRAY(String))


# Apply the hook at the field level
@strawchemy.type(Fruit, exclude={"color"})
class FruitTypeWithDescription:
    instance: ModelInstance[Fruit]

    # Use QueryHook to ensure specific columns are loaded
    @strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.adjectives]))
    def description(self) -> str:
        return f"The {self.instance.name} is {', '.join(self.instance.adjectives)}"


# Create a custom query hook for filtering
class FilterFruitHook(QueryHook[Fruit]):
    def apply_hook(self, statement: Select[tuple[Fruit]], alias: AliasedClass[Fruit]) -> Select[tuple[Fruit]]:
        # Add a custom WHERE clause
        return statement.where(alias.name == "Apple")


# Apply the hook at the type level
@strawchemy.type(Fruit, exclude={"color"}, query_hook=FilterFruitHook())
class FilteredFruitType:
    pass
```

Important notes when implementing `apply_hooks`:

- You must use the provided `alias` parameter to refer to columns of the model on which the hook is applied. Otherwise,
  the statement may fail.
- The GraphQL context is available through `self.info` within hook methods.
- You must set a `ModelInstance` typed attribute if you want to access the model instance values.
  The `instance` attribute is matched by the `ModelInstance[Fruit]` type hint, so you can give it any name you want.

### Load specific columns/relationships

The `load` parameter specify columns and relationships that should always be loaded, even if not directly requested in
the GraphQL query. This is useful for:

- Ensuring data needed for computed properties is available
- Loading columns or relationships required for custom resolvers

Examples of using the `load` parameter:

```python
# Load specific columns
@strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.adjectives]))
def description(self) -> str:
    return f"The {self.instance.name} is {', '.join(self.instance.adjectives)}"


# Load a relationship without specifying columns
@strawchemy.field(query_hook=QueryHook(load=[Fruit.farms]))
def pretty_farms(self) -> str:
    return f"Farms are: {', '.join(farm.name for farm in self.instance.farms)}"


# Load a relationship with specific columns
@strawchemy.field(query_hook=QueryHook(load=[(Fruit.color, [Color.name, Color.created_at])]))
def pretty_color(self) -> str:
    return f"Color is {self.instance.color.name}" if self.instance.color else "No color!"


# Load nested relationships
@strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [(Fruit.farms, [FruitFarm.name])])]))
def farms(self) -> str:
    return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"
```

</details>
