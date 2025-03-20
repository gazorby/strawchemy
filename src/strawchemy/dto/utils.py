"""Utilities for DTO configuration and type checking.

This module provides utility functions for configuring Data Transfer Objects (DTOs)
and performing type checks, specifically for optional type hints.

It exports the following:

- `config`: Configures a DTOConfig object for a specific purpose.
- `field`: Configures a DTOFieldConfig object for a specific purpose.
- `is_type_hint_optional`: Checks if a type hint is optional.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .constants import DTO_INFO_KEY
from .types import DTOConfig, DTOFieldConfig, ExcludeFields, IncludeFields, Purpose, PurposeConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = (
    "PRIVATE",
    "READ_ONLY",
    "WRITE_ONLY",
    "config",
    "field",
    "read_all_config",
    "read_all_partial_config",
    "read_partial",
    "write_all_config",
    "write_all_partial_config",
)


def config(
    purpose: Purpose,
    include: IncludeFields | None = None,
    exclude: ExcludeFields | None = None,
    partial: bool | None = None,
    type_map: Mapping[Any, Any] | None = None,
    aliases: Mapping[str, str] | None = None,
    alias_generator: Callable[[str], str] | None = None,
) -> DTOConfig:
    config = DTOConfig(purpose, alias_generator=alias_generator)
    if exclude:
        config.exclude = exclude
    if include:
        config.include = include
    if type_map:
        config.type_overrides = type_map
    if aliases:
        config.aliases = aliases
    if partial is not None:
        config.partial = partial
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


read_partial = DTOConfig(Purpose.READ, partial=True)
read_all_config = DTOConfig(Purpose.READ, include="all")
read_all_partial_config = DTOConfig(Purpose.READ, include="all", partial=True)
write_all_config = DTOConfig(Purpose.WRITE, include="all")
write_all_partial_config = DTOConfig(Purpose.WRITE, include="all", partial=True)

READ_ONLY = field({Purpose.READ})
WRITE_ONLY = field({Purpose.WRITE})
PRIVATE = field(set())
