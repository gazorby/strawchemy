"""Base validation module for Strawchemy framework.

This module provides the foundational components for input validation in Strawchemy,
including protocols and base exceptions for validation operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

if TYPE_CHECKING:
    from strawchemy.dto.base import MappedDTO
    from strawchemy.strawberry.mutation.types import ValidationErrorType

T = TypeVar("T")


class InputValidationError(Exception):
    """Exception raised when input validation fails.

    This exception wraps the original validation error and provides a method to convert
    it to a GraphQL-compatible error type.

    Attributes:
        validation: The validation protocol instance that failed
        exception: The original exception that was raised during validation
    """

    def __init__(self, validation: ValidationProtocol[Any], exception: Exception) -> None:
        """Initialize with the validation instance and original exception.

        Args:
            validation: The validation protocol instance that failed
            exception: The original exception that was raised
        """
        self.validation = validation
        self.exception = exception

    def graphql_type(self) -> ValidationErrorType:
        """Convert the validation error to a GraphQL-compatible error type.

        Returns:
            A GraphQL-compatible error type that can be returned in a response
        """
        return self.validation.to_error(self.exception)


class ValidationProtocol(Protocol, Generic[T]):
    """Protocol defining the interface for validation classes.

    This protocol specifies the required methods that validation classes must implement
    to be compatible with Strawchemy's validation system.
    """

    def validate(self, **kwargs: Any) -> MappedDTO[T]:
        """Validate the input data and return a mapped DTO if successful.

        Args:
            **kwargs: The input data to validate

        Returns:
            A mapped DTO containing the validated data

        Raises:
            Exception: If validation fails
        """
        raise NotImplementedError

    def to_error(self, exception: Any) -> ValidationErrorType:
        """Convert a validation exception to a GraphQL-compatible error type.

        Args:
            exception: The exception to convert

        Returns:
            A GraphQL-compatible error type
        """
        raise NotImplementedError
