from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    from typing import Any

__all__ = ("SessionNotFoundError", "StrawchemyError")


class StrawchemyError(Exception):
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


class SessionNotFoundError(StrawchemyError): ...
