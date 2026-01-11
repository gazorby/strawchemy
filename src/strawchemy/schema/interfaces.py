from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

import strawberry


class ErrorId(Enum):
    ERROR = "ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    LOCALIZED_VALIDATION_ERROR = "LOCALIZED_VALIDATION_ERROR"


@strawberry.interface(description="Base interface for expected errors", name="ErrorType")
class ErrorType:
    """Base class for GraphQL errors."""

    __error_types__: ClassVar[set[type[Any]]] = set()

    id: str = ErrorId.ERROR.value

    def __init_subclass__(cls) -> None:
        if not cls.__error_types__:
            cls.__error_types__.add(ErrorType)
        cls.__error_types__.add(cls)
