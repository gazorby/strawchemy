"""DTO domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


__all__ = ("DTOConfig", "DTOFieldConfig", "Purpose")


class DTOMissingType:
    """A sentinel type to detect if a parameter is supplied or not when.

    constructing pydantic FieldInfo.
    """


DTO_MISSING = DTOMissingType()


class Purpose(str, Enum):
    """For identifying the purpose of a DTO to the factory.

    The factory will exclude fields marked as private or read-only on the domain model depending
    on the purpose of the DTO.

    Example:
    ```python
    ReadDTO = dto.factory("AuthorReadDTO", Author, purpose=dto.Purpose.READ)
    ```
    """

    READ = "read"
    """To mark a DTO that is to be used to serialize data returned to
    clients."""
    WRITE = "write"
    """To mark a DTO that is to deserialize and validate data provided by
    clients."""
    COMPLETE = "complete"
    """To mark a DTO that is to deserialize and validate data provided by
    clients. Fields marked as TO_COMPLETE must not be null."""


@dataclass
class PurposeConfig:
    """Mark the field as read-only, or private."""

    type_override: Any | None = DTO_MISSING
    validator: Callable[[Any], Any] | None = None
    """Single argument callables that are defined on the DTO as validators for the field."""
    alias: str | None = None
    """Customize name of generated pydantic field."""
    partial: bool | None = None


@dataclass
class DTOFieldConfig:
    """For configuring DTO behavior on SQLAlchemy model fields."""

    purposes: set[Purpose] = field(default_factory=lambda: {Purpose.READ, Purpose.WRITE})
    default_config: PurposeConfig = field(default_factory=PurposeConfig)
    configs: dict[Purpose, PurposeConfig] = field(default_factory=dict)

    def purpose_config(self, dto_config: DTOConfig) -> PurposeConfig:
        return self.configs.get(dto_config.purpose, self.default_config)


@dataclass
class DTOConfig:
    """Control the generated DTO."""

    purpose: Purpose
    """Configure the DTO for "read" or "write" operations."""
    exclude: set[str] = field(default_factory=set)
    """Explicitly exclude fields from the generated DTO."""
    partial: bool | None = None
    """Make all field optional."""
    type_map: Mapping[Any, Any] = field(default_factory=dict)

    aliases: Mapping[str, str] = field(default_factory=dict)

    alias_generator: Callable[[str], str] | None = None

    def __post_init__(self) -> None:
        if self.aliases and self.alias_generator is not None:
            msg = "You must set `aliases` or `alias_generator`, not both"
            raise ValueError(msg)

    def alias(self, name: str) -> str | None:
        if self.aliases:
            return self.aliases.get(name)
        if self.alias_generator is not None:
            return self.alias_generator(name)
        return None

    @property
    def cache_key(self) -> int:
        return hash(
            (self.purpose, self.partial, self.alias_generator, tuple(self.type_map), tuple(self.type_map.values()))
        )
