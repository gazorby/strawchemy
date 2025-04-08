from __future__ import annotations

from typing import Any, TypeVar

import strawberry
from strawberry import UNSET
from strawchemy.dto.base import MappedDTO
from strawchemy.graphql.mutation import (
    RequiredToManyUpdateInputMixin,
    RequiredToOneInputMixin,
    ToManyCreateInputMixin,
    ToManyUpdateInputMixin,
    ToOneInputMixin,
)

T = TypeVar("T", bound=MappedDTO[Any])
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])


@strawberry.input
class ToOneInput(ToOneInputMixin[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET


@strawberry.input
class RequiredToOneInput(RequiredToOneInputMixin[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET


@strawberry.input
class ToManyCreateInput(ToManyCreateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET


@strawberry.input
class ToManyUpdateInput(ToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    remove: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET


@strawberry.input
class RequiredToManyUpdateInput(RequiredToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET
