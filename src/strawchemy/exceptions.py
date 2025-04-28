from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import ValidationError

__all__ = ("StrawchemyError",)


class StrawchemyError(Exception): ...


class InputValidationError(Exception):
    def __init__(self, pydantic_error: ValidationError) -> None:
        self.pydantic_error = pydantic_error
