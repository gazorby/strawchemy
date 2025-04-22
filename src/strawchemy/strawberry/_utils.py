from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, overload

from strawberry.experimental.pydantic import UnregisteredTypeException
from strawberry.experimental.pydantic.utils import get_strawberry_type_from_model
from strawberry.types.base import StrawberryContainer, StrawberryType
from strawberry.types.lazy_type import LazyType
from strawberry.types.union import StrawberryUnion

from .types import ErrorType

if TYPE_CHECKING:
    from strawberry import Info
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawchemy.strawberry.typing import StrawchemyTypeFromPydantic


__all__ = (
    "default_session_getter",
    "dto_model_from_type",
    "pydantic_from_strawberry_type",
    "strawchemy_type_from_pydantic",
)


def default_session_getter(info: Info[Any, Any]) -> Any:
    return info.context.session


def pydantic_from_strawberry_type(type_: type[StrawberryTypeFromPydantic[PydanticModel]]) -> type[PydanticModel]:
    return type_._pydantic_type  # pyright: ignore[reportAttributeAccessIssue]  # noqa: SLF001


@overload
def strawchemy_type_from_pydantic(
    type_: type[PydanticModel], strict: Literal[False]
) -> type[StrawchemyTypeFromPydantic[PydanticModel]] | None: ...


@overload
def strawchemy_type_from_pydantic(
    type_: type[PydanticModel], strict: Literal[True]
) -> type[StrawchemyTypeFromPydantic[PydanticModel]]: ...


@overload
def strawchemy_type_from_pydantic(
    type_: type[PydanticModel], strict: bool = False
) -> type[StrawchemyTypeFromPydantic[PydanticModel]] | None: ...


def strawchemy_type_from_pydantic(
    type_: type[PydanticModel], strict: bool = False
) -> type[StrawchemyTypeFromPydantic[PydanticModel]] | None:
    try:
        return get_strawberry_type_from_model(type_)
    except UnregisteredTypeException as error:
        if hasattr(type_, "_strawberry_input_type"):
            return type_._strawberry_input_type  # pyright: ignore[reportAttributeAccessIssue] # noqa: SLF001
        if strict:
            raise UnregisteredTypeException(type_) from error
        return None


def dto_model_from_type(type_: Any) -> Any:
    try:
        strawberry_type = pydantic_from_strawberry_type(type_)
    except AttributeError:
        strawberry_type = type_
    return strawberry_type.__dto_model__


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
