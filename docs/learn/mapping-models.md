# Mapping models

`@strawchemy.type` builds a GraphQL type from a SQLAlchemy model. This page covers choosing its fields, adding your own, and overriding the types Strawchemy generates.

## Exposing a model

`@strawchemy.type` turns a SQLAlchemy model into a GraphQL type. Two lines expose every column and relationship on `User`:

```python
@strawchemy.type(User, include="all")
class UserType: ...
```

## Choosing fields

```python
@strawchemy.type(User, include=["id", "name"])
class UserType: ...
```

Or map every field except one:

```python
@strawchemy.type(User, exclude=["email"])
class UserType: ...
```

## Field groups

`include` and `exclude` also accept group selectors, importable from `strawchemy`, instead of listing field names one by one:

- `SCALARS` — every column field
- `RELATIONSHIPS` — every relationship field
- `ALL` — both; equivalent to `include=[SCALARS, RELATIONSHIPS]`

A bare constant or a list mixing groups and field names both work:

```python
from strawchemy import RELATIONSHIPS, SCALARS


@strawchemy.type(User, include=SCALARS)
class UserType: ...


@strawchemy.type(User, include=[SCALARS, "posts"])
class UserType: ...
```

The first keeps only `id`, `name` and `email`; the second adds the `posts` relationship on top of the columns. Groups work the same way in `exclude` — excluding a group leaves everything else included by default:

```python
@strawchemy.type(User, exclude=RELATIONSHIPS)
class UserType: ...
```

`include` and `exclude` can be combined: a field is kept when `include` selects it and `exclude` doesn't.

```python
@strawchemy.type(User, include=SCALARS, exclude=["email"])
class UserType: ...
```

## Custom fields

A `ModelInstance[User]` attribute gives a resolver access to the underlying model instance. `@strawchemy.field` doubles as a method decorator, not just a function you call: decorating a method exposes it as a GraphQL field alongside the auto-generated ones. The statement Strawchemy builds loads what the client selected, not what the method reads, so pass a `QueryHook` naming what the method needs — `name` and `email` here:

```python
from strawchemy import ModelInstance, QueryHook


@strawchemy.type(User, include="all")
class UserType:
    instance: ModelInstance[User]

    @strawchemy.field(query_hook=QueryHook(load=[User.name, User.email]))
    def display_name(self) -> str:
        return f"{self.instance.name} <{self.instance.email}>"
```

Without the hook, `{ users { displayName } }` fails with `sqlalchemy.exc.MissingGreenlet` unless the client also selects `name` and `email` (a sync session instead runs one extra query per row). A relationship always needs the hook, since relationships the client selects are not set on the instance:

```python
    @strawchemy.field(query_hook=QueryHook(load=[User.posts]))
    def post_count(self) -> int:
        return len(self.instance.posts)
```

`load` takes columns or relationships, but the rule is the same either way: whatever the method reads, the hook declares.

A decorated method may return any type, a plain `@strawberry.type` included; a `strawchemy.field()` declared without one needs a Strawchemy type, as covered in [which types a field accepts](/learn/strawchemy-and-strawberry#which-types-a-field-accepts).

See [query hooks](/learn/query-hooks) for what `QueryHook` can do, and [custom resolvers](/learn/resolvers) for the other options `@strawchemy.field` accepts.

## Overriding generated types

Mapping `UserType` with `include="all"` doesn't stop at `User`: it walks the `posts` relationship and auto-generates a default `PostType`. Declaring your own `PostType` afterward gives you a second type over the same model — but only with `override=True`:

```python
@strawchemy.type(Post, include="all")  # [!code error]
class PostType: ...
```

Without `override=True`, this raises at class-decoration time:

```
strawchemy.exceptions.StrawchemyError: Type `PostType` is already registered
```

```python
@strawchemy.type(Post, include="all", override=True)
class PostType: ...
```

`override=True` tells Strawchemy to use your definition instead of the generated one.

## Reusing the same type

`scope="schema"` is an alternative to `override=True`, not an addition to it: instead of overriding the auto-generated type after the fact, it registers your type as the canonical one for a model and purpose (a `type`, `filter`, `input`, …) up front, so nothing auto-generates one to override. Declare `TagType` as schema-scoped before anything maps `Post`, and its `tags` field picks it up automatically. Include only `SCALARS`, not `"all"` — a relationship field on a schema-scoped type would still walk into its target model and auto-register a type for it, the same collision `override=True` exists to solve:

```python
@strawchemy.type(Tag, include=SCALARS, scope="schema")
class TagType: ...


@strawchemy.type(Post, include=["id", "title", "tags"])
class PostType: ...
```

## Mapping strictness

By default (`strict=True`), a column with no GraphQL mapping fails only when `strawberry.Schema(...)` builds the schema; the class itself decorates without complaint. A `complex` column stored through SQLAlchemy's `PickleType` is one such column:

```python
from sqlalchemy import PickleType
from sqlalchemy.orm import Mapped, mapped_column


class Widget(Base):
    __tablename__ = "widget"

    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[complex] = mapped_column(PickleType)


@strawchemy.type(Widget, include="all")
class WidgetType: ...
```

```python
@strawberry.type
class Query:
    widgets: list[WidgetType] = strawchemy.field()


schema = strawberry.Schema(query=Query)  # [!code error]
```

```
TypeError: WidgetType fields cannot be resolved. Unexpected type '<class 'complex'>'
```

Set `strict=False` on the config and the same column is dropped from the type instead, with a warning as its only trace:

```python
strawchemy = Strawchemy(StrawchemyConfig("sqlite", strict=False))
```

```
Skipping Widget.payload: no GraphQL mapping for <class 'complex'>
```
