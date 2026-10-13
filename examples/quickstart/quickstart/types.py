from __future__ import annotations

from quickstart.models import Post, Tag, User
from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemyConfig

strawchemy = Strawchemy(StrawchemyConfig("sqlite", repository_type=StrawchemyAsyncRepository))


@strawchemy.filter(User, include="all")
class UserFilter: ...


@strawchemy.filter(Post, include="all", scope="schema")
class PostFilter: ...


@strawchemy.order(User, include="all")
class UserOrderBy: ...


@strawchemy.order(Post, include="all", scope="schema")
class PostOrderBy: ...


@strawchemy.type(User, include="all")
class UserType: ...


@strawchemy.type(Post, include="all", scope="schema")
class PostType: ...


@strawchemy.type(Tag, include="all", scope="schema")
class TagType: ...


@strawchemy.create_input(Post, include=["title", "content", "views"])
class PostCreateInput: ...
