"""Utilities for DTO configuration and type checking.

This module provides utility functions for configuring Data Transfer Objects (DTOs)
and performing type checks, specifically for optional type hints.

It exports the following:

- `config`: Configures a DTOConfig object for a specific purpose.
- `field`: Configures a DTOFieldConfig object for a specific purpose.
- `is_type_hint_optional`: Checks if a type hint is optional.
"""

from __future__ import annotations

from types import UnionType
from typing import TYPE_CHECKING, Any, Optional, Union, get_args, get_origin

from .constants import DTO_INFO_KEY
from .types import DTOConfig, DTOFieldConfig, ExcludeFields, IncludeFields, Purpose, PurposeConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = (
    "config",
    "field",
    "is_type_hint_optional",
    "read_all_config",
    "read_all_partial_config",
    "write_all_config",
    "write_all_partial_config",
)

read_all_config = DTOConfig(Purpose.READ, include="all")
read_all_partial_config = DTOConfig(Purpose.READ, include="all", partial=True)
write_all_config = DTOConfig(Purpose.WRITE, include="all")
write_all_partial_config = DTOConfig(Purpose.WRITE, include="all", partial=True)


def config(
    purpose: Purpose,
    include: IncludeFields | None = None,
    exclude: ExcludeFields | None = None,
    partial: bool = False,
    type_map: Mapping[Any, Any] | None = None,
    aliases: Mapping[str, str] | None = None,
    alias_generator: Callable[[str], str] | None = None,
) -> DTOConfig:
    config = DTOConfig(purpose, partial=partial, alias_generator=alias_generator)
    if exclude:
        config.exclude = exclude
    if include:
        config.include = include
    if type_map:
        config.type_overrides = type_map
    if aliases:
        config.aliases = aliases
    return config


def field(
    purposes: set[Purpose] | None = None,
    default_config: PurposeConfig | None = None,
    configs: dict[Purpose, PurposeConfig] | None = None,
) -> dict[str, DTOFieldConfig]:
    return {
        DTO_INFO_KEY: DTOFieldConfig(
            purposes=purposes if purposes is not None else {Purpose.READ, Purpose.WRITE},
            default_config=default_config or PurposeConfig(),
            configs=configs or {},
        ),
    }


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
