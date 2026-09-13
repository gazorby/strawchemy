from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    from typing import Any

__all__ = (
    "DTOError",
    "EmptyDTOError",
    "GraphError",
    "ModelInspectorError",
    "QueryHookError",
    "QueryResultError",
    "SessionNotFoundError",
    "StrawchemyError",
    "StrawchemyFieldError",
    "TranspilingError",
)


class StrawchemyError(Exception):
    """Base class for every error raised by strawchemy."""

    detail: str

    def __init__(self, *args: Any, detail: str = "") -> None:
        """Initialize `StrawchemyError`.

        Args:
            *args: args are converted to `str` before passing to `Exception`
            detail: detail of the exception.
        """
        str_args = [str(arg) for arg in args if arg]
        if not detail:
            if str_args:
                detail, *str_args = str_args
            elif hasattr(self, "detail"):
                detail = self.detail
        self.detail = detail
        super().__init__(*str_args)

    @override
    def __repr__(self) -> str:
        if self.detail:
            return f"{self.__class__.__name__} - {self.detail}"
        return self.__class__.__name__

    @override
    def __str__(self) -> str:
        return " ".join((*self.args, self.detail)).strip()


class SessionNotFoundError(StrawchemyError):
    """Raised when no session can be resolved from the GraphQL context."""


class StrawchemyFieldError(StrawchemyError):
    """Raised when a schema field is declared with an unusable configuration."""


class DTOError(StrawchemyError):
    """Raised when an error occurs while generating or using a DTO."""


class EmptyDTOError(DTOError):
    """Raised when a DTO would be generated without any field."""


class ModelInspectorError(DTOError):
    """Raised when a model field cannot be inspected as requested."""


class TranspilingError(StrawchemyError):
    """Raised when an error occurs during transpiling."""


class QueryResultError(StrawchemyError):
    """Raised when an error occurs during query result processing or mapping."""


class QueryHookError(StrawchemyError):
    """Raised when an error occurs within a query hook's execution."""


class GraphError(StrawchemyError):
    """Raised when a query graph node is missing an expected relative or metadata."""
