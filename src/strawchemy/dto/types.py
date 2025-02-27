"""DTO domain types."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


__all__ = ("DTO_AUTO", "DTO_MISSING", "DTOConfig", "DTOFieldConfig", "ExcludeFields", "IncludeFields", "Purpose")

IncludeFields: TypeAlias = list[str] | set[str] | Literal["all"]
ExcludeFields: TypeAlias = list[str] | set[str]


class DTOMissingType:
    """A sentinel type to detect if a parameter is supplied or not when.

    constructing pydantic FieldInfo.
    """


class DTOAutoType: ...


DTO_MISSING = DTOMissingType()
DTO_AUTO = DTOAutoType()


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
    """Customize name of generated DTO field."""
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
    include: IncludeFields = field(default_factory=set)
    """Explicitly include fields from the generated DTO."""
    exclude: ExcludeFields = field(default_factory=set)
    """Explicitly exclude fields from the generated DTO. Implies `include="all"`."""
    partial: bool | None = None
    """Make all field optional."""
    type_overrides: Mapping[Any, Any] = field(default_factory=dict)
    annotation_overrides: dict[str, Any] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)

    alias_generator: Callable[[str], str] | None = None

    def __post_init__(self) -> None:
        if self.aliases and self.alias_generator is not None:
            msg = "You must set `aliases` or `alias_generator`, not both"
            raise ValueError(msg)
        if self.include and self.include != "all" and self.exclude:
            msg = "When using `exclude` you must set `include='all' or leave it unset`"
            raise ValueError(msg)
        if self.exclude:
            self.include = "all"

    def with_base_annotations(self, base: type[Any]) -> DTOConfig:
        """Merge type annotations from a base class into this DTOConfig.

        Args:
            base: The base class to extract type annotations from

        Returns:
            A new DTOConfig instance with:
            - Type annotations from the base class merged into annotation_overrides
            - Updated include set to include all fields if exclude is specified or include was "all"

        The method handles two cases:
        1. When include is "all" or exclude is specified: All fields from the base class are included
        2. When specific fields are included: Only those fields are added to the include set
        """
        include: set[str] = set(self.include) if self.include != "all" else set()
        include_all = self.include == "all" or self.exclude
        annotation_overrides: dict[str, Any] = self.annotation_overrides
        try:
            base_annotations = get_type_hints(base)
        except NameError:
            base_annotations = base.__annotations__
        for name, annotation in base_annotations.items():
            if not include_all:
                include.add(name)
            annotation_overrides[name] = annotation
        return dataclasses.replace(
            self,
            include="all" if include_all else include,
            annotation_overrides=annotation_overrides,
        )

    def alias(self, name: str) -> str | None:
        if self.aliases:
            return self.aliases.get(name)
        if self.alias_generator is not None:
            return self.alias_generator(name)
        return None
