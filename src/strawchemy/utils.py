from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from re import Pattern


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


def snake_keys(dct: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert dict keys to from camel case to snake case."""
    res: dict[Any, Any] = {}
    for k, v in dct.items():
        to_snake: str = camel_to_snake(k)
        if isinstance(v, list | tuple):
            res[to_snake] = [snake_keys(el) for el in v]
        elif isinstance(v, dict):
            res[to_snake] = snake_keys(v)
        else:
            res[to_snake] = v
    return res
