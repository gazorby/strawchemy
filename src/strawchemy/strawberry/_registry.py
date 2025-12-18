from __future__ import annotations

import dataclasses
from collections import defaultdict
from copy import copy
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    ForwardRef,
    Literal,
    NewType,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
)

from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.base import StrawberryContainer
from strawberry.types.field import StrawberryField

import strawberry
from strawchemy.strawberry._utils import strawberry_contained_types

try:
    from strawchemy.strawberry.filters.geo import GeoComparison

    geo_comparison = GeoComparison
except ModuleNotFoundError:  # pragma: no cover
    geo_comparison = None

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterable, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.schema.config import StrawberryConfig
    from strawberry.types.arguments import StrawberryArgument
    from strawberry.types.base import WithStrawberryObjectDefinition

    from strawchemy.dto.types import DTOScope
    from strawchemy.strawberry.typing import GraphQLType, StrawchemyTypeWithStrawberryObjectDefinition
    from strawchemy.types import DefaultOffsetPagination


__all__ = ("RegistryTypeInfo", "StrawberryRegistry")

T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)

_RegistryMissing = NewType("_RegistryMissing", object)


@dataclasses.dataclass
class _TypeReference:
    ref_holder: StrawberryField | StrawberryArgument

    @classmethod
    def _replace_contained_type(
        cls, container: StrawberryContainer, strawberry_type: type[WithStrawberryObjectDefinition]
    ) -> StrawberryContainer:
        """Recursively replace the contained type in a StrawberryContainer.

        Args:
            container: The container to replace the type in.
            strawberry_type: The type to replace with.

        Returns:
            A new container with the type replaced.
        """
        container_copy = copy(container)
        if isinstance(container.of_type, StrawberryContainer):
            replaced = cls._replace_contained_type(container.of_type, strawberry_type)
        else:
            replaced = strawberry_type
        container_copy.of_type = replaced
        return container_copy

    def _set_type(self, strawberry_type: type[WithStrawberryObjectDefinition] | StrawberryContainer) -> None:
        """Set the type of the referenced field or argument.

        Args:
            strawberry_type: The type to set.
        """
        if isinstance(self.ref_holder, StrawberryField):
            self.ref_holder.type = strawberry_type
        self.ref_holder.type_annotation = StrawberryAnnotation(
            strawberry_type,
            namespace=self.ref_holder.type_annotation.namespace if self.ref_holder.type_annotation else None,
        )

    def update_type(self, strawberry_type: type[WithStrawberryObjectDefinition]) -> None:
        """Update the type of the referenced field or argument.

        If the referenced type is a container, it will recursively replace the contained type.

        Args:
            strawberry_type: The type to update to.
        """
        if isinstance(self.ref_holder.type, StrawberryContainer):
            self._set_type(self._replace_contained_type(self.ref_holder.type, strawberry_type))
        else:
            self._set_type(strawberry_type)


@dataclasses.dataclass(frozen=True, eq=True)
class RegistryTypeInfo:
    name: str
    graphql_type: GraphQLType
    default_name: str | None = None
    user_defined: bool = False
    override: bool = False
    pagination: DefaultOffsetPagination | Literal[False] = False
    order_by: bool = False
    scope: DTOScope | None = None
    model: type[DeclarativeBase] | None = None
    tags: frozenset[str] = dataclasses.field(default_factory=frozenset)
    exclude_from_scope: bool = False

    @property
    def scoped_id(self) -> Hashable:
        return (self.model, self.graphql_type, self.tags)


class StrawberryRegistry:
    def __init__(self, strawberry_config: StrawberryConfig) -> None:
        self.strawberry_config = strawberry_config
        self._namespaces: defaultdict[GraphQLType, dict[str, type[StrawchemyTypeWithStrawberryObjectDefinition]]] = (
            defaultdict(dict)
        )
        self._forward_type_refs: defaultdict[GraphQLType, defaultdict[str, list[_TypeReference]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._type_refs: defaultdict[Hashable, list[_TypeReference]] = defaultdict(list)
        self._scoped_types: dict[Hashable, type[StrawchemyTypeWithStrawberryObjectDefinition]] = {}
        self._type_map: dict[RegistryTypeInfo, type[Any]] = {}
        self._names_map: defaultdict[GraphQLType, dict[str, RegistryTypeInfo]] = defaultdict(dict)
        self._tracked_type_names: defaultdict[GraphQLType, set[str]] = defaultdict(set)

    def _get_field_type_name(
        self,
        field: StrawberryField | StrawberryArgument,
        inner_type: Any,
        graphql_type: GraphQLType,
    ) -> str | None:
        """Get the type name of a field.

        This will handle forward references and get the object definition if available.

        Args:
            field: The field or argument to get the type name from.
            inner_type: The inner type of the field.
            graphql_type: The graphql type of the field.

        Returns:
            The type name of the field, or None if it cannot be resolved.
        """
        if field.type_annotation:
            for type_ in self._inner_types(field.type_annotation.raw_annotation):
                if isinstance(type_, (str, ForwardRef)):
                    field.type_annotation.namespace = self.namespace(graphql_type)
                    return type_.__forward_arg__ if isinstance(type_, ForwardRef) else type_

        if field_type_def := get_object_definition(inner_type):
            return field_type_def.name

        return None

    def _update_references(self, field: StrawberryField | StrawberryArgument, graphql_type: GraphQLType) -> None:
        """Update the references of a field.

        This will resolve forward references and update the type of the field if necessary.

        Args:
            field: The field or argument to update the references of.
            graphql_type: The graphql type of the field.
        """
        for inner_type in strawberry_contained_types(field.type):
            field_type_name = self._get_field_type_name(field, inner_type, graphql_type)
            if not field_type_name:
                continue

            type_ref = _TypeReference(field)
            type_info = self.get(graphql_type, field_type_name, None)

            if type_info and not type_info.exclude_from_scope:
                self._type_refs[type_info.scoped_id].append(type_ref)
                if scoped_type := self._scoped_types.get(type_info.scoped_id):
                    type_ref.update_type(scoped_type)

            if type_info is None or not type_info.override:
                self._forward_type_refs[graphql_type][field_type_name].append(type_ref)
            else:
                type_ref.update_type(self._type_map[type_info])

            if get_object_definition(inner_type):
                self._track_references(inner_type, graphql_type)

    def _track_references(
        self,
        strawberry_type: type[WithStrawberryObjectDefinition | StrawberryTypeFromPydantic[PydanticModel]],
        graphql_type: GraphQLType,
        force: bool = False,
    ) -> None:
        """Track the references of a strawberry type.

        This will recursively track the references of all fields and arguments of the given type.

        Args:
            strawberry_type: The type to track the references of.
            graphql_type: The graphql type of the type.
            force: Whether to force tracking the references even if the type has already been tracked.
        """
        object_definition = get_object_definition(strawberry_type, strict=True)
        schema_name = self.strawberry_config.name_converter.get_name_from_type(strawberry_type)
        if not force and schema_name in self._tracked_type_names[graphql_type]:
            return
        self._tracked_type_names[graphql_type].add(schema_name)
        for field in object_definition.fields:
            for argument in field.arguments:
                if any(
                    get_object_definition(inner_type) is not None
                    for inner_type in strawberry_contained_types(argument.type)
                ):
                    self._update_references(argument, "input")
            self._update_references(field, graphql_type)

    def _register_type(self, type_info: RegistryTypeInfo, strawberry_type: type[Any]) -> None:
        """Register a type in the registry.

        This will add the type to the namespace, update forward references, and track the references of the type.

        Args:
            type_info: The type info of the type to register.
            strawberry_type: The type to register.
        """
        self.namespace(type_info.graphql_type)[type_info.name] = strawberry_type
        if type_info.override or type_info.scope == "global":
            for reference in self._forward_type_refs[type_info.graphql_type][type_info.name]:
                reference.update_type(strawberry_type)
        self._track_references(strawberry_type, type_info.graphql_type, force=type_info.override)
        if type_info.scope == "global" and type_info.model:
            if type_info.default_name:
                self._namespaces[type_info.graphql_type][type_info.default_name] = strawberry_type
            for reference in self._type_refs[type_info.scoped_id]:
                reference.update_type(strawberry_type)
            self._scoped_types[type_info.scoped_id] = strawberry_type
        self._names_map[type_info.graphql_type][type_info.name] = type_info
        self._type_map[type_info] = strawberry_type

    @classmethod
    def _inner_types(cls, typ: Any) -> tuple[Any, ...]:
        """Get innermost types in typ.

        List[Optional[str], Union[Mapping[int, float]]] -> (str, int, float)

        Args:
            typ: A type annotation

        Returns:
            All inner types found after walked in all outer types
        """
        origin = get_origin(typ)
        if not origin or not hasattr(typ, "__args__"):
            return (typ,)
        arg_types = []
        for arg_type in get_args(typ):
            arg_types.extend(cls._inner_types(arg_type))
        return tuple(arg_types)

    def _get(self, type_info: RegistryTypeInfo) -> type[Any] | None:
        """Get a type from the registry.

        This will return the type if it exists and is an override, or if it is not an override and a non-override type with the same info exists.

        Args:
            type_info: The type info of the type to get.

        Returns:
            The type if it exists, otherwise None.
        """
        if (existing := self.get(type_info.graphql_type, type_info.name, None)) and existing.override:
            return self._type_map[existing]
        if not type_info.override and (existing := self._type_map.get(type_info)):
            return existing
        return None

    def _check_conflicts(self, type_info: RegistryTypeInfo) -> None:
        """Check for conflicts in the registry.

        This will raise a ValueError if a conflict is found.

        Args:
            type_info: The type info to check for conflicts with.
        """
        if (
            self.non_override_exists(type_info)
            or self.namespace("enum").get(type_info.name)
            or self.name_clash(type_info)
        ):
            msg = f"Type {type_info.name} is already registered"
            raise ValueError(msg)

    def __contains__(self, type_info: RegistryTypeInfo) -> bool:
        return type_info in self._type_map

    def name_clash(self, type_info: RegistryTypeInfo) -> bool:
        return (
            type_info not in self
            and (existing := self.get(type_info.graphql_type, type_info.name, None)) is not None
            and not existing.override
            and not type_info.override
        )

    @overload
    def get(self, graphql_type: GraphQLType, name: str, default: _RegistryMissing) -> RegistryTypeInfo: ...

    @overload
    def get(self, graphql_type: GraphQLType, name: str) -> RegistryTypeInfo: ...

    @overload
    def get(self, graphql_type: GraphQLType, name: str, default: T) -> RegistryTypeInfo | T: ...

    def get(self, graphql_type: GraphQLType, name: str, default: T = _RegistryMissing) -> RegistryTypeInfo | T:
        if default is _RegistryMissing:
            return self._names_map[graphql_type][name]
        return self._names_map[graphql_type].get(name, default)

    def non_override_exists(self, type_info: RegistryTypeInfo) -> bool:
        # A user defined type with the same name, that is not marked as override already exists
        return dataclasses.replace(type_info, user_defined=True, override=False) in self or (
            dataclasses.replace(type_info, user_defined=False, override=False) in self
            and not type_info.override
            and type_info.user_defined
        )

    def namespace(self, graphql_type: GraphQLType) -> dict[str, type[Any]]:
        return self._namespaces[graphql_type]

    def register_type(
        self,
        type_: type[Any],
        type_info: RegistryTypeInfo,
        description: str | None = None,
        directives: Sequence[object] | None = (),
    ) -> type[Any]:
        self._check_conflicts(type_info)
        if has_object_definition(type_):
            return type_
        if existing := self._get(type_info):
            return existing

        strawberry_type = strawberry.type(
            type_,
            name=type_info.name,
            is_input=type_info.graphql_type == "input",
            is_interface=type_info.graphql_type == "interface",
            description=description,
            directives=directives,
        )
        self._register_type(type_info, strawberry_type)
        return strawberry_type

    def register_enum(
        self,
        enum_type: type[EnumT],
        name: str | None = None,
        description: str | None = None,
        directives: Iterable[object] = (),
    ) -> type[EnumT]:
        type_name = name or f"{enum_type.__name__}Enum"
        if existing := self.namespace("enum").get(type_name):
            return cast("type[EnumT]", existing)
        strawberry_enum_type = strawberry.enum(cls=enum_type, name=name, description=description, directives=directives)
        self.namespace("enum")[type_name] = strawberry_enum_type

        return strawberry_enum_type
