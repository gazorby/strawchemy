from __future__ import annotations

import dataclasses
from collections import defaultdict
from copy import copy
from enum import Enum
from typing import TYPE_CHECKING, Any, ForwardRef, NewType, TypeVar, cast, overload

import strawberry
from strawberry import LazyType
from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.base import StrawberryContainer
from strawberry.types.field import StrawberryField
from strawberry.types.union import StrawberryUnion

from strawchemy.dto.strawberry import MappedStrawberryGraphQLDTO
from strawchemy.dto.types import FieldGroupStr, cast_include_fields, is_fields_iterable
from strawchemy.exceptions import StrawchemyError
from strawchemy.utils.annotation import inner_types
from strawchemy.utils.strawberry import strawberry_contained_types

try:
    from strawchemy.schema.filters.geo import GeoComparison

    geo_comparison = GeoComparison
except ModuleNotFoundError:  # pragma: no cover
    geo_comparison = None

if TYPE_CHECKING:
    from collections.abc import Hashable, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.schema.config import StrawberryConfig
    from strawberry.types.arguments import StrawberryArgument
    from strawberry.types.base import WithStrawberryObjectDefinition

    from strawchemy.dto import DTOConfig
    from strawchemy.dto.base import Node, Relation
    from strawchemy.dto.strawberry import EnumDTO, OrderByDTO, StrawchemyObject
    from strawchemy.dto.types import DTOScope, FieldSelector, IncludeFields
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.typing import GraphQLType, StrawchemyObjectWithStrawberryObjectDefinition

__all__ = ("RegistryTypeInfo", "StrawberryRegistry")

T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)
StrawchemyDTOT = TypeVar("StrawchemyDTOT", bound="StrawchemyObject")

_RegistryMissing = NewType("_RegistryMissing", object)


@dataclasses.dataclass(frozen=True, slots=True)
class _TypeReference:
    """Reference to a type used by a field or argument, used to update it later."""

    ref_holder: StrawberryField | StrawberryArgument
    """The field or argument whose type holds the referenced type."""
    target: Any = None
    """The inner type (class, `LazyType`, forward ref) this reference was created for.

    Used to match the right member when the referenced type is part of a `StrawberryUnion`.
    """
    target_name: str | None = None
    """The registry name the reference is keyed under.

    Fallback for matching a union member when `target` identity does not hold
    (e.g. the member annotation was re-resolved).
    """

    def _matches_target(self, member: Any) -> bool:
        """Check whether a union member is the one this reference was created for."""
        if member is self.target:
            return True
        if self.target_name is None:
            return False
        if isinstance(member, LazyType):
            return member.type_name == self.target_name
        member_definition = get_object_definition(member)
        return member_definition is not None and member_definition.name == self.target_name

    def _replaced_union(
        self, union: StrawberryUnion, strawberry_type: type[WithStrawberryObjectDefinition]
    ) -> StrawberryUnion:
        """Return a copy of the union with only the matching member replaced.

        The member is matched by identity against the reference target, falling back
        to a name comparison. If no member matches, the union is returned unchanged
        """
        annotations = list(union.type_annotations)
        for index, member in enumerate(union.types):
            if self._matches_target(member):
                annotations[index] = StrawberryAnnotation(strawberry_type, namespace=annotations[index].namespace)
                union_copy = copy(union)
                union_copy.type_annotations = tuple(annotations)
                return union_copy
        return union

    def _replaced(
        self, node: Any, strawberry_type: type[WithStrawberryObjectDefinition]
    ) -> type[WithStrawberryObjectDefinition] | StrawberryContainer | StrawberryUnion:
        """Recursively replace the referenced type within containers and unions.

        Containers are copied with their inner type replaced; unions are rebuilt with
        only the matching member swapped; any other node is replaced directly.
        """
        if isinstance(node, StrawberryContainer):
            container_copy = copy(node)
            container_copy.of_type = self._replaced(node.of_type, strawberry_type)
            return container_copy
        if isinstance(node, StrawberryUnion):
            return self._replaced_union(node, strawberry_type)
        return strawberry_type

    def _set_type(
        self, strawberry_type: type[WithStrawberryObjectDefinition] | StrawberryContainer | StrawberryUnion
    ) -> None:
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

        Containers are recursed into; union members are replaced individually (a
        union field is never replaced wholesale).

        Args:
            strawberry_type: The type to update to.
        """
        self._set_type(self._replaced(self.ref_holder.type, strawberry_type))


@dataclasses.dataclass(frozen=True, eq=True)
class RegistryTypeInfo:
    name: str
    graphql_type: GraphQLType
    default_name: str | None = None
    user_defined: bool = False
    override: bool = False
    pagination: DefaultOffsetPagination | None = None
    order: frozenset[FieldSelector] | FieldGroupStr | type[OrderByDTO] = dataclasses.field(default_factory=frozenset)
    distinct_on: frozenset[FieldSelector] | FieldGroupStr | type[EnumDTO] = dataclasses.field(default_factory=frozenset)
    paginate: frozenset[FieldSelector] | FieldGroupStr = dataclasses.field(default_factory=frozenset)
    scope: DTOScope | None = None
    model: type[DeclarativeBase] | None = None
    tags: frozenset[str] = dataclasses.field(default_factory=frozenset)
    exclude_from_scope: bool = False

    @property
    def scoped_id(self) -> Hashable:
        return self.model, self.graphql_type, self.tags


class StrawberryRegistry:
    def __init__(self, strawberry_config: StrawberryConfig) -> None:
        self.strawberry_config = strawberry_config
        self._namespaces: defaultdict[GraphQLType, dict[str, type[StrawchemyObjectWithStrawberryObjectDefinition]]] = (
            defaultdict(dict)
        )
        self._forward_type_refs: defaultdict[GraphQLType, defaultdict[str, list[_TypeReference]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._type_refs: defaultdict[Hashable, list[_TypeReference]] = defaultdict(list)
        self._scoped_types: dict[Hashable, type[StrawchemyObjectWithStrawberryObjectDefinition]] = {}
        self._type_map: dict[RegistryTypeInfo, type[Any]] = {}
        self._names_map: defaultdict[GraphQLType, dict[str, RegistryTypeInfo]] = defaultdict(dict)
        self._tracked_type_names: defaultdict[GraphQLType, set[str]] = defaultdict(set)
        self._unique_names: defaultdict[str, int] = defaultdict(int)

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
            for type_ in inner_types(field.type_annotation.raw_annotation):
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
        for inner_type in strawberry_contained_types(field.type, resolve_lazy=False):
            if isinstance(inner_type, LazyType):
                field_type_name: str | None = inner_type.type_name
            else:
                field_type_name = self._get_field_type_name(field, inner_type, graphql_type)
            if not field_type_name:
                continue

            type_ref = _TypeReference(field, target=inner_type, target_name=field_type_name)
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
                    for inner_type in strawberry_contained_types(argument.type, resolve_lazy=False)
                ):
                    self._update_references(argument, "input")
            self._update_references(field, graphql_type)

    def _register(self, type_info: RegistryTypeInfo, strawberry_type: type[Any]) -> None:
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
        if type_info.graphql_type != "enum":
            self._track_references(strawberry_type, type_info.graphql_type, force=type_info.override)
        if type_info.scope == "global" and type_info.model:
            if type_info.default_name:
                self._namespaces[type_info.graphql_type][type_info.default_name] = strawberry_type
            for reference in self._type_refs[type_info.scoped_id]:
                reference.update_type(strawberry_type)
            self._scoped_types[type_info.scoped_id] = strawberry_type
        self._names_map[type_info.graphql_type][type_info.name] = type_info
        self._type_map[type_info] = strawberry_type

    def _get(self, type_info: RegistryTypeInfo) -> type[Any] | None:
        """Get a type from the registry.

        This will return the type if it exists and is an override, or if it is not an override and a non-override type with the same info exists.

        Args:
            type_info: The type info of the type to get.

        Returns:
            The type if it exists, otherwise None.
        """
        if (
            not type_info.override
            and (existing := self.get(type_info.graphql_type, type_info.name, None))
            and existing.override
        ):
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
            or (type_info.graphql_type != "enum" and self.namespace("enum").get(type_info.name))
            or self._name_clash(type_info)
        ):
            msg = f"Type `{type_info.name}` is already registered"
            raise StrawchemyError(msg)

    def __contains__(self, type_info: RegistryTypeInfo) -> bool:
        return type_info in self._type_map

    def _name_clash(self, type_info: RegistryTypeInfo) -> bool:
        return (
            type_info not in self
            and (existing := self.get(type_info.graphql_type, type_info.name, None)) is not None
            and not existing.override
            and not type_info.override
        )

    def _type_info(
        self,
        dto: type[StrawchemyObject | Enum],
        graphql_type: GraphQLType,
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, Any], None] | None,
        override: bool = False,
        user_defined: bool = False,
        paginate: IncludeFields | None = None,
        order: IncludeFields | type[OrderByDTO] | None = None,
        distinct_on: IncludeFields | type[EnumDTO] | None = None,
        default_pagination: DefaultOffsetPagination | None = None,
        default_name: str | None = None,
    ) -> RegistryTypeInfo:
        model: type[DeclarativeBase] | None = (
            cast("type[DeclarativeBase]", dto.__dto_model__) if issubclass(dto, MappedStrawberryGraphQLDTO) else None
        )
        type_info = RegistryTypeInfo(
            name=dto.__name__,
            default_name=default_name,
            graphql_type=graphql_type,
            override=override,
            user_defined=user_defined,
            pagination=default_pagination,
            order=cast_include_fields(order) if is_fields_iterable(order) else order,
            distinct_on=cast_include_fields(distinct_on) if is_fields_iterable(distinct_on) else distinct_on,
            paginate=cast_include_fields(paginate),
            scope=dto_config.scope,
            model=model,
            exclude_from_scope=dto_config.exclude_from_scope,
        )
        if self._name_clash(type_info) and current_node is not None:
            type_info = dataclasses.replace(
                type_info, name="".join(node.value.name for node in current_node.path_from_root())
            )
        return type_info

    def uniquify_name(self, graphql_type: GraphQLType, name: str) -> str:
        """Return a type name guaranteed to be unique within the registry."""
        while self.get(graphql_type, name, None):
            self._unique_names[name] += 1
            name = f"{name}{self._unique_names[name]}"
        return name

    @overload
    def get(self, graphql_type: GraphQLType, name: str, default: _RegistryMissing) -> RegistryTypeInfo: ...

    @overload
    def get(self, graphql_type: GraphQLType, name: str) -> RegistryTypeInfo: ...

    @overload
    def get(self, graphql_type: GraphQLType, name: str, default: T) -> RegistryTypeInfo | T: ...

    def get(
        self, graphql_type: GraphQLType, name: str, default: T | type[_RegistryMissing] = _RegistryMissing
    ) -> RegistryTypeInfo | T:
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
        dto: type[StrawchemyDTOT],
        graphql_type: GraphQLType,
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, Any], None] | None = None,
        override: bool = False,
        user_defined: bool = False,
        paginate: IncludeFields | None = None,
        order: IncludeFields | type[OrderByDTO] | None = None,
        distinct_on: IncludeFields | type[EnumDTO] | None = None,
        default_pagination: DefaultOffsetPagination | None = None,
        default_name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
    ) -> type[StrawchemyDTOT]:
        type_info = self._type_info(
            dto=dto,
            graphql_type=graphql_type,
            dto_config=dto_config,
            current_node=current_node,
            override=override,
            user_defined=user_defined,
            paginate=paginate,
            order=order,
            distinct_on=distinct_on,
            default_pagination=default_pagination,
            default_name=default_name,
        )
        self._check_conflicts(type_info)
        if has_object_definition(dto):
            return dto
        if existing := self._get(type_info):
            return existing

        strawberry_type = cast(
            "type[StrawchemyDTOT]",
            strawberry.type(
                dto,
                name=type_info.name,
                is_input=type_info.graphql_type == "input",
                is_interface=type_info.graphql_type == "interface",
                description=description or dto.__strawchemy_definition__.description,
                directives=directives,
            ),
        )
        self._register(type_info, strawberry_type)
        return strawberry_type

    def register_enum(
        self,
        enum_type: type[EnumT],
        dto_config: DTOConfig,
        override: bool = False,
        user_defined: bool = False,
        default_name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] = (),
    ) -> type[EnumT]:
        type_info = self._type_info(
            dto=enum_type,
            graphql_type="enum",
            dto_config=dto_config,
            override=override,
            user_defined=user_defined,
            default_name=default_name,
            current_node=None,
        )
        self._check_conflicts(type_info)
        if existing := self._get(type_info):
            return cast("type[EnumT]", existing)

        strawberry_type = strawberry.enum(
            cls=enum_type, name=type_info.name, description=description, directives=directives
        )
        self._register(type_info, strawberry_type)
        return strawberry_type
