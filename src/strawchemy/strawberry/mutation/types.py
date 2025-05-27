from __future__ import annotations

from enum import Enum, auto
from typing import Any, ClassVar, Generic, TypeVar, override

import strawberry
from strawberry import UNSET
from strawberry.types import get_object_definition
from strawchemy.dto.base import MappedDTO, ToMappedProtocol, VisitorProtocol
from strawchemy.dto.types import DTO_UNSET, DTOUnsetType

__all__ = ("RelationType",)

T = TypeVar("T", bound=MappedDTO[Any])
RelationInputT = TypeVar("RelationInputT", bound=MappedDTO[Any])

_TO_ONE_DESCRIPTION = "Add a new or existing object"
_TO_MANY_DESCRIPTION = "Add new or existing objects"
_TO_MANY_UPDATE_DESCRIPTION = "Add new objects or update existing ones"


def error_type_names() -> set[str]:
    return {get_object_definition(type_, strict=True).name for type_ in ErrorType.__error_types__}


class ErrorId(Enum):
    ERROR = "ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    LOCALIZED_VALIDATION_ERROR = "LOCALIZED_VALIDATION_ERROR"


class RelationType(Enum):
    TO_ONE = auto()
    TO_MANY = auto()


@strawberry.input(description=_TO_ONE_DESCRIPTION)
class ToOneInput(ToMappedProtocol[Any], Generic[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET

    @override
    def to_mapped(
        self,
        visitor: VisitorProtocol[Any] | None = None,
        override: dict[str, Any] | None = None,
        level: int = 0,
    ) -> Any | DTOUnsetType:
        if self.create and self.set:
            msg = "You cannot use both `set` and `create` in a -to-one relation input"
            raise ValueError(msg)
        return self.create.to_mapped(visitor, level=level, override=override) if self.create else DTO_UNSET


@strawberry.input(description=_TO_ONE_DESCRIPTION)
class RequiredToOneInput(ToOneInput[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET

    @override
    def to_mapped(
        self,
        visitor: VisitorProtocol[Any] | None = None,
        override: dict[str, Any] | None = None,
        level: int = 0,
    ) -> Any | DTOUnsetType:
        if not self.create and not self.set:
            msg = "Relation is required, you must set either `set` or `create`."
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level, override=override)


@strawberry.input(description=_TO_MANY_DESCRIPTION)
class ToManyCreateInput(ToMappedProtocol[Any], Generic[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET

    @override
    def to_mapped(
        self,
        visitor: VisitorProtocol[Any] | None = None,
        override: dict[str, Any] | None = None,
        level: int = 0,
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add):
            msg = "You cannot use `set` with `create` or `add` in -to-many relation input"
            raise ValueError(msg)
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


@strawberry.input(description=_TO_MANY_UPDATE_DESCRIPTION)
class RequiredToManyUpdateInput(ToMappedProtocol[Any], Generic[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET

    @override
    def to_mapped(
        self,
        visitor: VisitorProtocol[Any] | None = None,
        override: dict[str, Any] | None = None,
        level: int = 0,
    ) -> list[Any] | DTOUnsetType:
        return (
            [dto.to_mapped(visitor, level=level, override=override) for dto in self.create]
            if self.create
            else DTO_UNSET
        )


@strawberry.input(description=_TO_MANY_UPDATE_DESCRIPTION)
class ToManyUpdateInput(RequiredToManyUpdateInput[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    remove: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET

    @override
    def to_mapped(
        self,
        visitor: VisitorProtocol[Any] | None = None,
        override: dict[str, Any] | None = None,
        level: int = 0,
    ) -> list[Any] | DTOUnsetType:
        if self.set and (self.create or self.add or self.remove):
            msg = "You cannot use `set` with `create`, `add` or `remove` in a -to-many relation input"
            raise ValueError(msg)
        return super().to_mapped(visitor, level=level, override=override)


@strawberry.interface(description="Base interface for expected errors", name="ErrorType")
class ErrorType:
    """Base class for GraphQL errors."""

    __error_types__: ClassVar[set[type[Any]]] = set()

    id: str = ErrorId.ERROR.value

    def __init_subclass__(cls) -> None:
        if not cls.__error_types__:
            cls.__error_types__.add(ErrorType)
        cls.__error_types__.add(cls)


@strawberry.type(description="Indicate validation error type and location.", name="LocalizedErrorType")
class LocalizedErrorType(ErrorType):
    """Match inner shape of pydantic ValidationError."""

    id = ErrorId.LOCALIZED_VALIDATION_ERROR.value
    loc: list[str] = strawberry.field(default_factory=list)
    message: str
    type: str


@strawberry.type(description="Input is malformed or invalid.", name="ValidationErrorType")
class ValidationErrorType(ErrorType):
    """Input is malformed or invalid."""

    id = ErrorId.VALIDATION_ERROR.value
    errors: list[LocalizedErrorType]
