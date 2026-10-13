"""Union field whose schema-scoped members must not rewrite the field type (no lazy).

Same shape as ``union_override_lazy`` but both union members are direct class
references. Registering the ``scope="schema"`` member types must keep the field typed
as the union.
"""

from __future__ import annotations

from typing import Annotated, Union

import strawberry

from strawchemy import Strawchemy
from tests.unit.models import Group, Tag, User

strawchemy = Strawchemy("postgresql")


@strawchemy.type(Group, include=["id"], scope="schema")
class GroupNode:
    pass


@strawchemy.type(Tag, include=["id"], scope="schema")
class TagNode:
    pass


ChildUnion = Annotated[
    Union[GroupNode, TagNode],
    strawberry.union("ChildUnion"),
]


@strawchemy.type(User, include=["id"], scope="schema")
class ParentNode:
    @strawberry.field(graphql_type=ChildUnion | None)
    def parent(self) -> object | None:
        return None


@strawberry.type
class Query:
    parent: ParentNode | None = None
