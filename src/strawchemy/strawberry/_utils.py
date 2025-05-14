from __future__ import annotations

from typing import TYPE_CHECKING, Any

from strawberry.types.base import StrawberryContainer, StrawberryType
from strawberry.types.lazy_type import LazyType
from strawberry.types.union import StrawberryUnion

from .mutation.types import ErrorType

if TYPE_CHECKING:
    from strawberry import Info


__all__ = ("default_session_getter", "dto_model_from_type")


def default_session_getter(info: Info[Any, Any]) -> Any:
    return info.context.session


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
