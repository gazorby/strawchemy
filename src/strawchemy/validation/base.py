from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

if TYPE_CHECKING:
    from strawchemy.dto.base import MappedDTO
    from strawchemy.strawberry.mutation.types import ValidationErrorType

T = TypeVar("T")


class InputValidationError(Exception):
    def __init__(self, validation: ValidationProtocol[Any], exception: Exception) -> None:
        self.validation = validation
        self.exception = exception

    def graphql_type(self) -> ValidationErrorType:
        return self.validation.to_error(self.exception)


class ValidationProtocol(Protocol, Generic[T]):
    def validate(self, **kwargs: Any) -> MappedDTO[T]:
        raise NotImplementedError

    def to_error(self, exception: Any) -> ValidationErrorType:
        raise NotImplementedError
