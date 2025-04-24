from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

import strawberry
from strawberry import UNSET
from strawberry.types import get_object_definition
from strawchemy.dto.base import MappedDTO
from strawchemy.graphql.mutation import (
    RequiredToManyUpdateInputMixin,
    RequiredToOneInputMixin,
    ToManyCreateInputMixin,
    ToManyUpdateInputMixin,
    ToOneInputMixin,
)
from strawchemy.utils import snake_to_lower_camel_case

if TYPE_CHECKING:
    from pydantic import ValidationError
    from pydantic_core import ErrorDetails


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


@strawberry.input(description=_TO_ONE_DESCRIPTION)
class ToOneInput(ToOneInputMixin[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET


@strawberry.input(description=_TO_ONE_DESCRIPTION)
class RequiredToOneInput(RequiredToOneInputMixin[T, RelationInputT]):
    set: T | None = UNSET
    create: RelationInputT | None = UNSET


@strawberry.input(description=_TO_MANY_DESCRIPTION)
class ToManyCreateInput(ToManyCreateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET


@strawberry.input(description=_TO_MANY_UPDATE_DESCRIPTION)
class ToManyUpdateInput(ToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    remove: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET


@strawberry.input(description=_TO_MANY_UPDATE_DESCRIPTION)
class RequiredToManyUpdateInput(RequiredToManyUpdateInputMixin[T, RelationInputT]):
    set: list[T] | None = UNSET
    add: list[T] | None = UNSET
    create: list[RelationInputT] | None = UNSET


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

    @classmethod
    def _to_localized_error(cls, errors: ErrorDetails, to_camel: bool) -> LocalizedErrorType:
        return LocalizedErrorType(
            loc=[snake_to_lower_camel_case(str(loc)) if to_camel else str(loc) for loc in errors["loc"]],
            message=errors["msg"],
            type=errors["type"],
        )

    @classmethod
    def from_pydantic(cls, exc: ValidationError, to_camel: bool = True) -> ValidationErrorType:
        return ValidationErrorType(errors=[cls._to_localized_error(err, to_camel) for err in exc.errors()])
