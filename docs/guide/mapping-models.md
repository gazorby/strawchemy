# Mapping SQLAlchemy Models

Strawchemy provides an easy way to map SQLAlchemy models to GraphQL types using the `@strawchemy.type` decorator. You
can include/exclude specific fields or have strawchemy map all columns/relationships of the model and it's children.

<details>
<summary>Mapping example</summary>

Include columns and relationships

```python
import strawberry
from strawchemy import Strawchemy

# Assuming these models are defined as in the Quick Start example
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

strawchemy = Strawchemy("postgresql")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


@strawchemy.type(User, include="all")
class UserType:
    pass
```

Including/excluding specific fields

```python
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    password: Mapped[str]


# Include specific fields
@strawchemy.type(User, include=["id", "name"])
class UserType:
    pass


# Exclude specific fields
@strawchemy.type(User, exclude=["password"])
class UserType:
    pass


# Include all fields
@strawchemy.type(User, include="all")
class UserType:
    pass
```

Add a custom fields

```python
from strawchemy import ModelInstance


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]


@strawchemy.type(User, include="all")
class UserType:
    instance: ModelInstance[User]

    @strawchemy.field
    def full_name(self) -> str:
        return f"{self.instance.first_name} {self.instance.last_name}"
```

See the [custom resolvers](/guide/resolvers) for more details

</details>

## Field Groups

Instead of listing field names one by one, `include` and `exclude` accept the `SCALARS` (column fields), `RELATIONSHIPS` (relation fields) and `ALL` group selectors, importable from `strawchemy`. They can be assigned directly (`include=SCALARS`), used inside an iterable, or mixed with field names — plain strings are always treated as field names.

<details>
<summary>Field group examples</summary>

```python
from strawchemy import ALL, RELATIONSHIPS, SCALARS


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    password: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


# Only column fields: id, name, password
@strawchemy.type(User, include=[SCALARS])
class UserType:
    pass


# Equivalent: a bare constant assigned directly
@strawchemy.type(User, include=SCALARS)
class UserType:
    pass


# Groups mix with field names: all columns plus the `posts` relationship
@strawchemy.type(User, include=[SCALARS, "posts"])
class UserType:
    pass


# Both groups together are equivalent to include=ALL
@strawchemy.type(User, include=[SCALARS, RELATIONSHIPS])
class UserType:
    pass


# Groups work in exclude too: a bare exclude implies everything else
# is included, so this keeps only the column fields
@strawchemy.type(User, exclude=[RELATIONSHIPS])
class UserType:
    pass
```

A group-bearing `include` can be combined with `exclude` to subtract fields from the group:

```python
# All columns except `password`
@strawchemy.type(User, include=[SCALARS], exclude=["password"])
class UserType:
    pass
```

`include` and `exclude` can always be combined: a field is kept when it is selected by `include` and not selected by `exclude`.

</details>

## Type Override

When generating types for relationships, Strawchemy creates default names (e.g., `<ModelName>Type`). If you have already
defined a Python class with that same name, it will cause a name collision.

The `override=True` parameter tells Strawchemy that your definition should be used, resolving the conflict.

<details>
<summary>Using `override=True`</summary>

Consider these models:

```python
class Author(Base):
    __tablename__ = "author"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class Book(Base):
    __tablename__ = "book"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship()
```

If you define a type for `Book`, Strawchemy will inspect the `author` relationship and attempt to auto-generate a type
for the `Author` model, naming it `AuthorType` by default. If you have already defined a class with that name, it will
cause a name collision.

```python
# Let's say you've already defined this class
@strawchemy.type(Book, include="all")
class BookType:
    pass


# This will cause an error because Strawchemy has already created `AuthorType` when generating `BookType`
@strawchemy.type(Book, include="all")
class AuthorType: ...
```

You would see an error like: `Type 'AuthorType' cannot be auto generated because it's already declared.`

To solve this, you can create a single, definitive `AuthorType` and mark it with `override=True`. This tells Strawchemy
to use your version instead of generating a new one.

```python
@strawchemy.type(Author, include="all", override=True)
class AuthorType:
    pass


# Now this works, because Strawchemy knows to use your `AuthorType`
@strawchemy.type(Book, include="all")
class BookType:
    pass
```

</details>

## Reuse types in schema

While `override=True` solves name collisions, `scope="global"` is used to promote consistency and reuse.

By defining a type with `scope="global"`, you register it as the canonical type for a given SQLAlchemy model and
purpose (e.g. a strawberry `type`, `filter`, or `input`). Strawchemy will then automatically use this globally-scoped
type everywhere it's needed in your schema, rather than generating new ones.

<details>
<summary>Using `scope="global"`</summary>

Let's define a global type for the `Color` model. This type will now be the default for the `Color` model across the
entire schema.

```python
# This becomes the canonical type for the `Color` model
@strawchemy.type(Color, include={"id", "name"}, scope="global")
class ColorType:
    pass


# Another type that references the Color model
@strawchemy.type(Fruit, include="all")
class FruitType:
    ...
    # Strawchemy automatically uses the globally-scoped `ColorType` here
    # without needing an explicit annotation.
```

This ensures that the `Color` model is represented consistently as `ColorType` in all parts of your GraphQL schema, such
as in the `FruitType`'s `color` field, without needing to manually specify it every time.

</details>
