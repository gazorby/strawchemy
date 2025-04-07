from __future__ import annotations

import re
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Any, Optional, Union, get_args, get_origin

if TYPE_CHECKING:
    from re import Pattern

__all__ = (
    "camel_to_snake",
    "is_type_hint_optional",
    "non_optional_type_hint",
    "snake_keys",
    "snake_to_camel",
    "snake_to_lower_camel_case",
)

_camel_to_snake_pattern: Pattern[str] = re.compile(r"((?<=[a-z0-9])[A-Z]|(?!^)(?<!_)[A-Z](?=[a-z]))")


def camel_to_snake(string: str) -> str:
    """Convert a camelcased string to snake case.

    See: https://stackoverflow.com/a/12867228
    """
    return _camel_to_snake_pattern.sub(r"_\1", string).lower()


def snake_to_camel(string: str) -> str:
    """Convert string to camel case.

    See: https://stackoverflow.com/a/19053800/10735573
    """
    return "".join(x.capitalize() for x in string.lower().split("_"))


def snake_to_lower_camel_case(snake_str: str) -> Any:
    """Convert string to lower camel case.

    See: https://stackoverflow.com/a/19053800/10735573
    """
    camel_string: str = snake_to_camel(snake_str)
    return snake_str[0].lower() + camel_string[1:]


def snake_keys(value: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert dict keys to from camel case to snake case."""
    res: dict[Any, Any] = {}
    for k, v in value.items():
        to_snake: str = camel_to_snake(k)
        if isinstance(v, list | tuple):
            res[to_snake] = [snake_keys(el) for el in v]
        elif isinstance(v, dict):
            res[to_snake] = snake_keys(v)
        else:
            res[to_snake] = v
    return res


def non_optional_type_hint(type_hint: Any) -> Any:
    origin, args = get_origin(type_hint), get_args(type_hint)
    if origin is Optional:
        return args
    if origin in (Union, UnionType):
        return Union[*tuple([arg for arg in args if arg not in (None, NoneType)])]
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
    if origin in (Union, UnionType):
        args = get_args(type_hint)
        return any(arg is type(None) for arg in args)
    return False
