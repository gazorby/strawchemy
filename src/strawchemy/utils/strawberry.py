from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, get_args, get_origin

from strawberry import Info, LazyType
from strawberry.types.base import (
    StrawberryContainer,
    StrawberryList,
    StrawberryOptional,
    StrawberryType,
    WithStrawberryObjectDefinition,
)
from strawberry.types.union import StrawberryUnion

from strawchemy.exceptions import SessionNotFoundError
from strawchemy.schema.interfaces import ErrorType
from strawchemy.typing import UNION_TYPES

if TYPE_CHECKING:
    from typing_extensions import TypeIs

_OPTIONAL_UNION_ARG_SIZE: int = 2


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


def is_list(
    type_: StrawberryType | type[WithStrawberryObjectDefinition] | object | str,
) -> TypeIs[type[list[Any]] | StrawberryList]:
    if isinstance(type_, StrawberryOptional):
        type_ = type_.of_type
    if origin := get_origin(type_):
        type_ = origin
        if origin is Optional:
            type_ = get_args(type_)[0]
        if origin in UNION_TYPES and len(args := get_args(type_)) == _OPTIONAL_UNION_ARG_SIZE:
            type_ = args[0] if args[0] is not type(None) else args[1]

    return isinstance(type_, StrawberryList) or type_ is list
