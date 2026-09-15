from __future__ import annotations

import strawberry

from quickstart.types import (
    PostCreateInput,
    PostFilter,
    PostOrderBy,
    PostType,
    UserFilter,
    UserOrderBy,
    UserType,
    strawchemy,
)


@strawberry.type
class Query:
    users: list[UserType] = strawchemy.field(filter_input=UserFilter, order_by_input=UserOrderBy, pagination=True)
    posts: list[PostType] = strawchemy.field(filter_input=PostFilter, order_by_input=PostOrderBy, pagination=True)


@strawberry.type
class Mutation:
    create_post: PostType = strawchemy.create(PostCreateInput)


schema = strawberry.Schema(query=Query, mutation=Mutation)
