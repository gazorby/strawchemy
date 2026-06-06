"""DTO domain types."""

from __future__ import annotations

import dataclasses
import functools
from dataclasses import InitVar, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, final, get_type_hints

from typing_extensions import Self, TypeIs, override

from strawchemy.utils.annotation import get_annotations

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from strawchemy.dto.base import DTOFieldDefinition


__all__ = (
    "ALL",
    "RELATIONSHIPS",
    "SCALARS",
    "DTOAuto",
    "DTOConfig",
    "DTOFieldConfig",
    "DTOMissing",
    "DTOScope",
    "DTOSkip",
    "DTOUnset",
    "FieldGroup",
    "FieldSelector",
    "FieldSpec",
    "Purpose",
    "PurposeConfig",
    "is_fields_iterable",
)

DTOScope: TypeAlias = Literal["global", "dto"]
FieldSelector: TypeAlias = "str | FieldGroup"
FieldIterable: TypeAlias = (
    "list[FieldSelector] | set[FieldSelector] | frozenset[FieldSelector] | tuple[FieldSelector, ...]"
)
FieldGroupStr: TypeAlias = Literal["all", "scalars", "relationships"]
FieldSpec: TypeAlias = "FieldIterable | FieldGroupStr | FieldGroup"
ConfigScope: TypeAlias = Literal["local", "global"]


class FieldGroup(Enum):
    """Field-group selectors for ``include``/``exclude`` sequences."""

    ALL = "all"
    """Include all fields from model."""
    SCALARS = "scalars"
    """Include everything but relationships."""
    RELATIONSHIPS = "relationships"
    """Include only relationships."""

    @staticmethod
    def list_str() -> str:
        return ", ".join(member.value for member in FieldGroup)

    @classmethod
    @functools.cache
    def values(cls) -> frozenset[str]:
        return frozenset(member.value for member in FieldGroup)

    @classmethod
    def is_group(cls, value: str) -> TypeIs[FieldGroupStr]:
        return value in cls.values()


@dataclass(slots=True)
class FieldSet:
    """Normalized, immutable view over a field selection.

    Wraps a `FieldSpec`, into a uniform `frozenset[FieldSelector]` so selections can be
    compared, hashed, and combined regardless of how they were originally
    expressed.
    """

    value: InitVar[FieldSpec | None]

    field_set: frozenset[FieldSelector] = field(init=False, default_factory=frozenset)

    def __post_init__(self, value: FieldSpec | None) -> None:
        self.field_set = self.normalize(value)

    def __next__(self) -> FieldSelector:
        return next(iter(self.field_set))

    def __iter__(self) -> Iterator[FieldSelector]:
        return iter(self.field_set)

    def __contains__(self, item: FieldSelector | DTOFieldDefinition[Any, Any]) -> bool:
        # A FieldGroup is only selected by itself or by ALL, never by group matching.
        if isinstance(item, FieldGroup):
            return item in self.field_set or FieldGroup.ALL in self.field_set
        name, is_relation = (item, False) if isinstance(item, str) else (item.model_field_name, item.is_relation)
        item_group = FieldGroup.RELATIONSHIPS if is_relation else FieldGroup.SCALARS
        return name in self.field_set or item_group in self.field_set or FieldGroup.ALL in self.field_set

    def __and__(self, other: FieldSpec) -> FieldIterable:
        other_set = FieldSet(other)
        # ALL subsumes any selection: intersecting with it yields the other side.
        if FieldGroup.ALL in self.field_set:
            return other_set.field_set
        if FieldGroup.ALL in other_set.field_set:
            return self.field_set
        return frozenset(field for field in self.field_set if field in other_set) | frozenset(
            field for field in other_set.field_set if field in self
        )

    def __or__(self, other: FieldSpec | None) -> FieldSpec | None:
        other_set = FieldSet(other)
        if FieldGroup.ALL in self.field_set or FieldGroup.ALL in other_set.field_set:
            return "all"
        return (self.field_set | other_set.field_set) or None

    def __bool__(self) -> bool:
        return bool(self.field_set)

    def __hash__(self) -> int:
        return hash(self.field_set)

    @classmethod
    def normalize(cls, value: FieldSpec | None) -> frozenset[FieldSelector]:
        """Normalize a field selection into a frozenset of selectors.

        Args:
            value: A group string ("all", "scalars", "relationships"), an
                iterable of field names and/or `FieldGroup` members, or `None`.

        Returns:
            Normalized field selector set
        """
        if isinstance(value, FieldGroup):
            return frozenset((value,))
        if isinstance(value, str) and FieldGroup.is_group(value):
            return frozenset((FieldGroup(value),))
        if value is None:
            return frozenset()
        return frozenset(value)


@final
class DTOMissing:
    """A sentinel type to detect if a parameter is supplied or not when.

    constructing pydantic FieldInfo.
    """


@final
class DTOAuto: ...


@final
class DTOSkip: ...


@final
class DTOUnset:
    @override
    def __str__(self) -> str:
        return ""

    @override
    def __repr__(self) -> str:
        return "DTOUnset"

    def __bool__(self) -> bool:
        return False


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


@dataclass(slots=True)
class PurposeConfig:
    """Mark the field as read-only, or private."""

    type_override: Any | None = DTOMissing
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


@dataclass(slots=True)
class DTOConfig:
    """Control the generated DTO.

    This class holds configuration settings that influence how a Data Transfer
    Object (DTO) is generated by the DTO factory. It allows customization of
    field inclusion/exclusion, optionality, type hints, and field aliasing based
    on the intended purpose (read, write, etc.) of the DTO.

    Attributes:
        purpose: Configure the DTO for "read", "write", or "complete" operations.
            Determines which fields from the source model are included based on
            their `DTOFieldConfig`.
        include: Explicitly include fields from the source model in the generated
            DTO. Can be a list or set of field names, and/or the `ALL` / `SCALARS` /
            `RELATIONSHIPS` group selectors, either assigned directly
            (`include=SCALARS`) or mixed with names inside an iterable (e.g.
            `[SCALARS, "owner"]`). `[SCALARS, RELATIONSHIPS]` is equivalent to
            `ALL`. Defaults to an empty set.
        exclude: Explicitly exclude fields from the source model. Can be a list or
            set of field names and/or the `ALL` / `SCALARS` / `RELATIONSHIPS` group
            selectors (e.g. `[RELATIONSHIPS]` keeps all scalar fields and walks no
            relationships). A bare `exclude` (no `include`) implies everything else
            is included. Defaults to an empty set.
        partial: If True, makes all fields in the generated DTO optional.
            Defaults to None.
        partial_default: The default value assigned to fields when `partial` is
            True and the field is not provided. Defaults to None.
        unset_sentinel: A sentinel object used to represent fields that are not
            set, particularly useful when distinguishing between a field explicitly
            set to `None` and a field that was not provided at all. Defaults to
            `DTO_UNSET`.
        type_overrides: A mapping to override the type annotations for specific
            fields in the generated DTO. Keys can be field names or types,
            values are the overriding types. Defaults to an empty dict.
        annotation_overrides: A dictionary to directly set or override the type
            annotations for specific fields by name. Defaults to an empty dict.
        aliases: A mapping of source model field names to their desired names
            (aliases) in the generated DTO. Defaults to an empty dict. Mutually
            exclusive with `alias_generator`.
        alias_generator: A callable that accepts a field name and returns its
            alias for the generated DTO. Defaults to None. Mutually exclusive
            with `aliases`.

    Raises:
        ValueError: If both `aliases` and `alias_generator` are provided, or
            if `exclude` is set while `include` is also set to a specific list/set
            (i.e., not "all" or empty).
    """

    purpose: Purpose
    """Configure the DTO for "read" or "write" operations."""
    include: FieldSpec | None = None
    """Explicitly include fields from the generated DTO."""
    exclude: FieldSpec | None = None
    """Explicitly exclude fields from the generated DTO. Implies everything else is included."""
    global_include: FieldSpec | None = None
    """Explicitly include fields from the generated DTO and all its children."""
    global_exclude: FieldSpec | None = None
    """Explicitly exclude fields from the generated DTO and all its children. Implies everything else is included."""
    partial: bool | None = None
    """Make all field optional."""
    partial_default: Any = None
    unset_sentinel: Any = DTOUnset
    type_overrides: Mapping[Any, Any] = field(default_factory=dict)
    annotation_overrides: dict[str, Any] = field(default_factory=dict)
    aliases: Mapping[str, str] = field(default_factory=dict)
    exclude_defaults: bool = False
    alias_generator: Callable[[str], str] | None = None
    scope: DTOScope | None = None
    exclude_from_scope: bool = False
    tags: set[str] = field(default_factory=set)

    included_fields: FieldSet = field(init=False)
    excluded_fields: FieldSet = field(init=False)

    def __post_init__(self) -> None:
        if self.aliases and self.alias_generator is not None:
            msg = "You must set `aliases` or `alias_generator`, not both"
            raise ValueError(msg)
        if self.include and not self._has_field_group(self.include) and self.exclude:
            msg = f"When using `exclude`, `include` must be unset or be a field group {FieldGroup.list_str()}."
            raise ValueError(msg)
        if self.global_include and not self._has_field_group(self.global_include) and self.global_exclude:
            msg = f"When using `global_exclude`, `global_include` must be unset or be a field group {FieldGroup.list_str()}."
            raise ValueError(msg)
        # A bare exclude (no include) means "everything except"; promote to "all".
        # If include carries a FieldGroup it is truthy, so the clobber is skipped.
        if self.global_exclude and self.global_include is None:
            self.global_include = "all"
        if self.exclude and self.include is None:
            self.include = "all"

        self.included_fields = FieldSet(self.global_include) if self.include is None else FieldSet(self.include)
        self.excluded_fields = FieldSet(self.global_exclude) if self.exclude is None else FieldSet(self.exclude)

    def __or__(self, other: DTOConfig) -> DTOConfig:
        return self.union(other)

    @classmethod
    def _has_field_group(cls, value: FieldSpec | FieldIterable) -> bool:
        """True if the selection contains a FieldGroup member."""
        if isinstance(value, FieldGroup):
            return True
        if isinstance(value, str):
            return value in FieldGroup.values()
        return any(isinstance(item, FieldGroup) for item in value)

    def union(self, other: DTOConfig) -> DTOConfig:
        include = FieldSet(self.include) | other.include
        exclude = FieldSet(self.exclude) | other.exclude
        global_include = FieldSet(self.global_include) | other.global_include
        global_exclude = FieldSet(self.global_exclude) | other.global_exclude
        type_overrides = dict(self.type_overrides) | dict(other.type_overrides)
        annotation_overrides = self.annotation_overrides | other.annotation_overrides
        tags = self.tags | other.tags

        return self.copy_with(
            include=include,
            global_include=global_include,
            exclude=exclude,
            global_exclude=global_exclude,
            type_overrides=type_overrides,
            annotation_overrides=annotation_overrides,
            tags=tags,
        )

    @classmethod
    def from_include(cls, include: FieldSpec | Literal[False] | None = None, purpose: Purpose = Purpose.READ) -> Self:
        """Create a DTOConfig from an include specification.

        Factory method for creating a DTOConfig with a simplified interface, converting
        an `IncludeFields` specification into a complete configuration object. This is
        useful for building configs when only the include/exclude specification matters.

        Args:
            include: The field inclusion specification. Can be:
                - None: Include no fields (converted to empty set)
                - "all": Include all fields
                - list or set of field names: Include only these specific fields
                Defaults to None.
            purpose: The purpose of the DTO being configured (READ, WRITE, or COMPLETE).
                Defaults to Purpose.READ.

        Returns:
            A new DTOConfig instance with the specified include and purpose settings.
            All other configuration parameters use their defaults.
        """
        return cls(purpose, include=include or set())

    def copy_with(
        self,
        purpose: Purpose | type[DTOUnset] = DTOUnset,
        include: FieldSpec | None = None,
        global_include: FieldSpec | None = None,
        exclude: FieldSpec | None = None,
        global_exclude: FieldSpec | None = None,
        partial: bool | None | type[DTOUnset] = DTOUnset,
        unset_sentinel: Any | type[DTOUnset] = DTOUnset,
        type_overrides: Mapping[Any, Any] | type[DTOUnset] = DTOUnset,
        annotation_overrides: dict[str, Any] | type[DTOUnset] = DTOUnset,
        aliases: Mapping[str, str] | type[DTOUnset] = DTOUnset,
        exclude_defaults: bool | type[DTOUnset] = DTOUnset,
        alias_generator: Callable[[str], str] | type[DTOUnset] = DTOUnset,
        partial_default: Any | type[DTOUnset] = DTOUnset,
        scope: DTOScope | type[DTOUnset] = DTOUnset,
        exclude_from_scope: bool | type[DTOUnset] = DTOUnset,
        tags: set[str] | type[DTOUnset] = DTOUnset,
    ) -> DTOConfig:
        """Create a copy of the DTOConfig with the specified changes."""
        if include is None and exclude is None:
            include, exclude = self.include, self.exclude
        else:
            include = include or set()
            exclude = exclude or set()
        if global_include is None and global_exclude is None:
            global_include, global_exclude = self.global_include, self.global_exclude
        else:
            global_include = global_include or set()
            global_exclude = global_exclude or set()
        return DTOConfig(
            include=include,
            exclude=exclude,
            global_include=global_include,
            global_exclude=global_exclude,
            purpose=self.purpose if purpose is DTOUnset else purpose,
            partial=self.partial if partial is DTOUnset else partial,
            unset_sentinel=self.unset_sentinel if unset_sentinel is DTOUnset else unset_sentinel,
            type_overrides=self.type_overrides if type_overrides is DTOUnset else type_overrides,
            annotation_overrides=self.annotation_overrides
            if annotation_overrides is DTOUnset
            else annotation_overrides,
            aliases=self.aliases if aliases is DTOUnset else aliases,
            exclude_defaults=self.exclude_defaults if exclude_defaults is DTOUnset else exclude_defaults,
            alias_generator=self.alias_generator if alias_generator is DTOUnset else alias_generator,
            partial_default=self.partial_default if partial_default is DTOUnset else partial_default,
            scope=self.scope if scope is DTOUnset else scope,
            exclude_from_scope=self.exclude_from_scope if exclude_from_scope is DTOUnset else exclude_from_scope,
            tags=self.tags if tags is DTOUnset else tags,
        )

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
        # Root-level include/exclude only: a global "all" must not pull base fields in.
        include_set = FieldSet(self.include)
        include = set(include_set.field_set)
        include_all = FieldGroup.ALL in include_set.field_set or bool(FieldSet(self.exclude))
        annotation_overrides: dict[str, Any] = self.annotation_overrides
        try:
            base_annotations = get_type_hints(base, include_extras=True)
        except NameError:
            base_annotations = get_annotations(base)
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

    def is_field_included(
        self, field: FieldSelector | DTOFieldDefinition[Any, Any], scope: ConfigScope | None = None
    ) -> bool:
        """Whether a field is included per the include/exclude rules.

        `field` is a field name or a `DTOFieldDefinition`. A bare `str` is treated as a non-relation field name.
        """
        if scope == "local":
            return field in FieldSet(self.include) and field not in FieldSet(self.exclude)
        if scope == "global":
            included = field in FieldSet(self.global_include) or FieldGroup.ALL in self.included_fields.field_set
            return included and field not in FieldSet(self.global_exclude)
        return field in self.included_fields and field not in self.excluded_fields


def is_fields_iterable(value: Any) -> TypeIs[FieldSpec]:
    """Test the given value is suitable to be used as either `include` or `exclude` in a DTOConfig."""
    if value == "all" or isinstance(value, FieldGroup):
        return True
    if isinstance(value, str):
        return False
    return isinstance(value, (frozenset, set, list, tuple))


ALL = FieldGroup.ALL
SCALARS = FieldGroup.SCALARS
RELATIONSHIPS = FieldGroup.RELATIONSHIPS
