from __future__ import annotations

import inspect
from typing import Any, NewType, Optional, TypeVar, Union, get_args, get_origin

from strawchemy.typing import UNION_TYPES

T = TypeVar("T", bound="Any")


def non_optional_type_hint(type_hint: Any) -> Any:
    origin, args = get_origin(type_hint), get_args(type_hint)
    if origin is Optional:
        return args
    if origin in UNION_TYPES:
        union_args = tuple([arg for arg in args if arg not in (None, type(None))])
        if len(union_args) == 1:
            return union_args[0]
        return Union[union_args]
    return type_hint


def is_type_hint_optional(type_hint: Any) -> bool:
    """Whether the given type hint is considered as optional or not.

    Returns:
        `True` if arguments of the given type hint are optional

    Three cases are considered:
    ```
        Optional[str]
        Union[str, None]
        str | None
    ```
    In any other form, the type hint will not be considered as optional
    """
    origin = get_origin(type_hint)
    if origin is None:
        return False
    if origin is Optional:
        return True
    if origin in UNION_TYPES:
        args = get_args(type_hint)
        return any(arg is type(None) for arg in args)
    return False


def get_annotations(obj: Any) -> dict[str, Any]:
    """Get the annotations of the given object."""
    return inspect.get_annotations(obj)


def new_type(name: str, type_: type[T]) -> type[T]:
    # Needed for pyright
    return NewType(name, type_)  # pyright: ignore[reportArgumentType]
