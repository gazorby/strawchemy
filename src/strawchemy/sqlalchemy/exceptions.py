"""SQLAlchemy DTO exceptions."""

from __future__ import annotations

__all__ = ("QueryHookError", "QueryResultError", "TranspilingError")


class TranspilingError(Exception):
    """Raised when an error occurs during transpiling."""


class QueryResultError(Exception): ...


class QueryHookError(Exception): ...
