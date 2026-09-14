# Getting started

## Installation

Strawchemy is available on PyPi

```console
pip install strawchemy
```

Strawchemy has the following optional dependencies:

- `geo` : Enable Postgis support through [geoalchemy2](https://github.com/geoalchemy/geoalchemy2)

To install these dependencies along with strawchemy:

```console
pip install strawchemy[geo]
```

## Quick Start

```python
import strawberry
from strawchemy import Strawchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Initialize the strawchemy mapper
strawchemy = Strawchemy("postgresql")


# Define SQLAlchemy models
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    author: Mapped[User] = relationship("User", back_populates="posts")


# Map models to GraphQL types
@strawchemy.type(User, include="all")
class UserType:
    pass


# override=True is needed because strawchemy automatically generates a PostType
# when mapping UserType due to the relationship between User and Post
@strawchemy.type(Post, include="all", override=True)
class PostType:
    pass


# Create filter inputs
@strawchemy.filter(User, include="all")
class UserFilter:
    pass


# override=True is needed for the same reason as PostType
# strawchemy generates filters for related models automatically
@strawchemy.filter(Post, include="all", override=True)
class PostFilter:
    pass


# Create order by inputs
@strawchemy.order(User, include="all")
class UserOrderBy:
    pass


@strawchemy.order(Post, include="all", override=True)
class PostOrderBy:
    pass


# Define GraphQL query fields
@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
    posts: list[PostType] = strawchemy.field(filter_input=PostFilter, order_by_input=PostOrderBy, pagination=True)


# Create schema
schema = strawberry.Schema(query=Query)
```

```graphql
{
    # Users with pagination, filtering, and ordering
    users(
        offset: 0
        limit: 10
        filter: { name: { contains: "John" } }
        orderBy: { name: ASC }
    ) {
        id
        name
        posts {
            id
            title
            content
        }
    }

    # Posts with exact title match
    posts(filter: { title: { eq: "Introduction to GraphQL" } }) {
        id
        title
        content
        author {
            id
            name
        }
    }
}
```
