from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn, Protocol

from strawchemy.exceptions import UnknownKeywordError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = ("reject_unknown_declaration_kwargs", "reject_unknown_kwargs")


class _TypedDictType(Protocol):
    __required_keys__: frozenset[str]
    __optional_keys__: frozenset[str]


def reject_unknown_kwargs(caller: str, kwargs: Mapping[str, object], accepted: _TypedDictType) -> None:
    """Reject a call to ``caller`` passing a keyword ``accepted`` does not declare.

    Raises:
        UnknownKeywordError: If ``kwargs`` holds such a keyword.
    """
    if (keyword := _unknown_keyword(kwargs, accepted)) is not None:
        msg = f"{caller}() got an unexpected keyword argument {keyword!r}"
        raise UnknownKeywordError(msg)


def reject_unknown_declaration_kwargs(
    model: type[Any], kwargs: Mapping[str, object], accepted: _TypedDictType
) -> Callable[[type[Any]], NoReturn] | None:
    """Return a decorator failing the declaration of its class if ``kwargs`` holds a keyword ``accepted`` lacks.

    The error is deferred to the decorated class so that its message can name it.
    """
    if (keyword := _unknown_keyword(kwargs, accepted)) is None:
        return None

    def reject(class_: type[Any]) -> NoReturn:
        msg = f"Unexpected keyword argument {keyword!r} when declaring {class_.__name__} ({model.__name__})"
        raise UnknownKeywordError(msg)

    return reject


def _unknown_keyword(kwargs: Mapping[str, object], accepted: _TypedDictType) -> str | None:
    known = accepted.__required_keys__ | accepted.__optional_keys__
    return next((key for key in kwargs if key not in known), None)
