from __future__ import annotations

from enum import Enum, auto
from typing import Any, Generic, TypeVar, override

from strawchemy.dto.base import MappedDTO, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.types import DTO_UNSET, DTOUnsetType

__all__ = (
    "RelationType",
    "RequiredToManyUpdateInputMixin",
    "RequiredToOneInputMixin",
    "ToManyCreateInputMixin",
    "ToManyUpdateInputMixin",
    "ToOneInputMixin",
)

T = TypeVar("T", bound=MappedDTO[Any])
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])


class RelationType(Enum):
    TO_ONE = auto()
    TO_MANY = auto()


class ToOneInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    set: T | None
    create: RelationInputT | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> Any | DTOUnsetType:
        if self.create and self.set:
            msg = "You cannot use both `set` and `create` in a -to-one relation input"
            raise ValueError(msg)
        return self.create.to_mapped(visitor, level=level, override=override) if self.create else DTO_UNSET


class RequiredToOneInputMixin(ToOneInputMixin[T, RelationInputT]):
    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> Any | DTOUnsetType:
        if not self.create and not self.set:
            msg = "Relation is required, you must set either `set` or `create`."
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level, override=override)


class ToManyCreateInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    set: list[T] | None
    add: list[T] | None
    create: list[RelationInputT] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add):
            msg = "You cannot use `set` with `create` or `add` in -to-many relation input"
            raise ValueError(msg)
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


class RequiredToManyUpdateInputMixin(ToMappedProtocol, Generic[T, RelationInputT]):
    add: list[T] | None
    create: list[RelationInputT] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


class ToManyUpdateInputMixin(RequiredToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None
    remove: list[T] | None

    @override
    def to_mapped(
        self, visitor: VisitorProtocol | None = None, override: dict[str, Any] | None = None, level: int = 0
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add or self.remove):
            msg = "You cannot use `set` with `create`, `add` or `remove` in a -to-many relation input"
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level, override=override)
