from __future__ import annotations

import strawberry
from strawberry import UNSET


@strawberry.input
class OneToOneInput:
    set: strawberry.ID | None


@strawberry.input
class OneToManyInput:
    set: strawberry.ID | None


@strawberry.input
class ToOneInput:
    add: list[strawberry.ID] | None = UNSET
    remove: list[strawberry.ID] | None = UNSET
    set: list[strawberry.ID] | None = UNSET


@strawberry.input
class ToManyInput:
    add: list[strawberry.ID] | None = UNSET
    remove: list[strawberry.ID] | None = UNSET
    set: list[strawberry.ID] | None = UNSET
