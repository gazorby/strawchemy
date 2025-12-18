from __future__ import annotations

from typing import TYPE_CHECKING, Any

from strawberry.types.base import StrawberryContainer, StrawberryType
from strawberry.types.lazy_type import LazyType
from strawberry.types.union import StrawberryUnion

from strawchemy.exceptions import SessionNotFoundError
from strawchemy.strawberry.mutation.types import ErrorType

if TYPE_CHECKING:
    from strawberry import Info


__all__ = ("default_session_getter", "dto_model_from_type")


def _get_or_subscribe(obj: Any, key: Any) -> Any:
    try:
        return getattr(obj, key)
    except AttributeError:
        try:
            return obj[key]
        except (TypeError, KeyError) as exc:
            raise SessionNotFoundError from exc


def default_session_getter(info: Info[Any, Any]) -> Any:
    """Try getting the session from the info context, then the request context."""
    try:
        return _get_or_subscribe(info.context, "session")
    except SessionNotFoundError:
        return _get_or_subscribe(_get_or_subscribe(info.context, "request"), "session")


def dto_model_from_type(type_: Any) -> Any:
    return type_.__dto_model__


def strawberry_contained_types(type_: StrawberryType | Any) -> tuple[Any, ...]:
    if isinstance(type_, LazyType):
        return strawberry_contained_types(type_.resolve_type())
    if isinstance(type_, StrawberryContainer):
        return strawberry_contained_types(type_.of_type)
    if isinstance(type_, StrawberryUnion):
        union_types = []
        for union_type in type_.types:
            union_types.extend(strawberry_contained_types(union_type))
        return tuple(union_types)
    return (type_,)


def strawberry_contained_user_type(type_: StrawberryType | Any) -> Any:
    inner_types = [
        inner_type for inner_type in strawberry_contained_types(type_) if inner_type not in ErrorType.__error_types__
    ]
    return inner_types[0]
