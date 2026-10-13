"""Union field whose schema-scoped members must not rewrite the field type.

``ParentNode.parent`` is declared as ``ChildUnion | None``, a Strawberry union of
``GroupNode`` and a ``strawberry.lazy`` reference to ``TagNode``. Registering the
``scope="schema"`` member types must keep the field typed as the union, swapping only
the matching member inside it.
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


ChildUnion = Annotated[
    Union[GroupNode, Annotated["TagNode", strawberry.lazy("tests.unit.schemas.union_override_lazy")]],
    strawberry.union("ChildUnion"),
]


@strawchemy.type(User, include=["id"], scope="schema")
class ParentNode:
    @strawberry.field(graphql_type=ChildUnion | None)
    def parent(self) -> object | None:
        return None


@strawchemy.type(Tag, include=["id"], scope="schema")
class TagNode:
    pass


@strawberry.type
class Query:
    parent: ParentNode | None = None
