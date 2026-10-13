from __future__ import annotations

import dataclasses
from collections import defaultdict
from copy import copy
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Any, ForwardRef, TypeVar, cast

import strawberry
from strawberry import LazyType
from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition
from strawberry.types.base import StrawberryContainer
from strawberry.types.enum import StrawberryEnumDefinition
from strawberry.types.field import StrawberryField
from strawberry.types.union import StrawberryUnion

from strawchemy.dto.strawberry import EnumDTO, MappedStrawberryGraphQLDTO
from strawchemy.dto.types import FieldSet
from strawchemy.exceptions import ScopeConflictError, TypeNameConflictError
from strawchemy.schema.field import RegistryAnnotation
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
    from strawchemy.dto.strawberry import OrderByDTO, StrawchemyObject
    from strawchemy.dto.types import DTOScope, FieldSpec
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.typing import GraphQLType, StrawchemyObjectWithStrawberryObjectDefinition

__all__ = ("RegistryTypeInfo", "StrawberryRegistry")

EnumT = TypeVar("EnumT", bound=Enum)
StrawchemyDTOT = TypeVar("StrawchemyDTOT", bound="StrawchemyObject")


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
    pagination: DefaultOffsetPagination | None = None
    order: FieldSet | type[OrderByDTO] = dataclasses.field(default_factory=frozenset)
    distinct_on: FieldSet | type[EnumDTO] = dataclasses.field(default_factory=frozenset)
    paginate: FieldSet = dataclasses.field(default_factory=frozenset)
    scope: DTOScope | None = None
    model: type[DeclarativeBase] | None = None
    scope_key: Hashable | None = dataclasses.field(default=None, compare=False)
    """Shared by the types a schema-scoped declaration stands in for; `None` keeps the type out of any scope."""


def _type_origin(type_: type[Any]) -> str:
    origin = f"`{type_.__module__}.{type_.__qualname__}`"
    if model := getattr(type_, "__dto_model__", None):
        return f"{origin} (model `{model.__name__}`)"
    return origin


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
        self._declared: set[RegistryTypeInfo] = set()
        self._declared_names: defaultdict[GraphQLType, set[str]] = defaultdict(set)
        self._displaced_names: dict[tuple[GraphQLType, str], str] = {}
        self._path_names: dict[RegistryTypeInfo, str] = {}

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
                    field.type_annotation = RegistryAnnotation(
                        field.type_annotation.raw_annotation,
                        registry_namespace_getter=partial(self.namespace, graphql_type),
                        namespace=field.type_annotation.namespace,
                    )
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
            target, inner_graphql_type = inner_type, graphql_type
            if isinstance(inner_type, LazyType):
                field_type_name: str | None = inner_type.type_name
            elif isinstance(inner_type, StrawberryEnumDefinition):
                field_type_name, target, inner_graphql_type = inner_type.name, inner_type.wrapped_cls, "enum"
            else:
                field_type_name = self._get_field_type_name(field, inner_type, graphql_type)
            if not field_type_name:
                continue

            type_ref = _TypeReference(field, target=target, target_name=field_type_name)
            type_info = self.get(inner_graphql_type, field_type_name)

            if type_info and type_info.scope_key is not None:
                self._type_refs[type_info.scope_key].append(type_ref)
                if scoped_type := self._scoped_types.get(type_info.scope_key):
                    type_ref.update_type(scoped_type)

            self._forward_type_refs[inner_graphql_type][field_type_name].append(type_ref)

            if get_object_definition(inner_type):
                self._track_references(inner_type, graphql_type)

    def _track_references(
        self,
        strawberry_type: type[WithStrawberryObjectDefinition | StrawberryTypeFromPydantic[PydanticModel]],
        graphql_type: GraphQLType,
    ) -> None:
        """Track the references of a strawberry type.

        This will recursively track the references of all fields and arguments of the given type.

        Args:
            strawberry_type: The type to track the references of.
            graphql_type: The graphql type of the type.
        """
        object_definition = get_object_definition(strawberry_type, strict=True)
        schema_name = self.strawberry_config.name_converter.get_name_from_type(strawberry_type)
        if schema_name in self._tracked_type_names[graphql_type]:
            return
        self._tracked_type_names[graphql_type].add(schema_name)
        for field in object_definition.fields:
            for argument in field.arguments:
                if any(
                    get_object_definition(inner_type) is not None or isinstance(inner_type, StrawberryEnumDefinition)
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
        if type_info.scope == "global":
            for reference in self._forward_type_refs[type_info.graphql_type][type_info.name]:
                reference.update_type(strawberry_type)
        if type_info.graphql_type != "enum":
            self._track_references(strawberry_type, type_info.graphql_type)
        if type_info.scope == "global" and type_info.scope_key is not None:
            if type_info.default_name:
                self._namespaces[type_info.graphql_type][type_info.default_name] = strawberry_type
            for reference in self._type_refs[type_info.scope_key]:
                reference.update_type(strawberry_type)
            self._scoped_types[type_info.scope_key] = strawberry_type
        self._names_map[type_info.graphql_type][type_info.name] = type_info
        self._type_map[type_info] = strawberry_type

    def _check_conflicts(self, type_info: RegistryTypeInfo, new_type: type[Any], *, declared: bool) -> None:
        """Check for conflicts in the registry.

        Args:
            type_info: The type info to check for conflicts with.
            new_type: The type about to be registered under `type_info`.
            declared: Whether `new_type` comes from a decorated class rather than being generated.

        Raises:
            TypeNameConflictError: If another type is already registered under the same name.
        """
        existing = None
        if self._name_clash(type_info) or (declared and type_info in self._declared):
            existing = self.namespace(type_info.graphql_type)[type_info.name]
        elif type_info.graphql_type != "enum":
            existing = self.namespace("enum").get(type_info.name)
        if existing is not None:
            msg = (
                f"Type `{type_info.name}` is already registered: "
                f"{_type_origin(existing)} conflicts with {_type_origin(new_type)}"
            )
            raise TypeNameConflictError(msg)

    def _claim(self, type_info: RegistryTypeInfo, new_type: type[Any], *, declared: bool) -> None:
        """Check that `new_type` can be registered under `type_info`, a declaration taking its name from generated types.

        Raises:
            TypeNameConflictError: If another type is already registered under the same name.
            ScopeConflictError: If another declaration already holds the schema scope `type_info` declares.
        """
        scoped = self._scoped_types.get(type_info.scope_key) if type_info.scope == "global" else None
        if scoped is not None:
            msg = (
                f"{_type_origin(new_type)} cannot declare the schema scope: "
                f"{_type_origin(scoped)} already declares it for the same model and kind"
            )
            raise ScopeConflictError(msg)
        if declared:
            self._displace(type_info.graphql_type, type_info.name)
        self._check_conflicts(type_info, new_type, declared=declared)
        if declared:
            self._declared.add(type_info)
            self._declared_names[type_info.graphql_type].add(type_info.name)

    def __contains__(self, type_info: RegistryTypeInfo) -> bool:
        return type_info in self._type_map

    def _name_clash(self, type_info: RegistryTypeInfo) -> bool:
        return type_info not in self and self.get(type_info.graphql_type, type_info.name) is not None

    def _type_info(
        self,
        dto: type[StrawchemyObject | Enum],
        graphql_type: GraphQLType,
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, Any], None] | None,
        *,
        paginate: FieldSpec | None = None,
        order: FieldSpec | type[OrderByDTO] | None = None,
        distinct_on: FieldSpec | type[EnumDTO] | None = None,
        default_pagination: DefaultOffsetPagination | None = None,
        default_name: str | None = None,
        declared: bool = False,
        scope_key: Hashable | None = None,
    ) -> RegistryTypeInfo:
        model: type[DeclarativeBase] | None = (
            cast("type[DeclarativeBase]", dto.__dto_model__)
            if issubclass(dto, (MappedStrawberryGraphQLDTO, EnumDTO))
            else None
        )
        type_info = RegistryTypeInfo(
            name=dto.__name__,
            default_name=default_name,
            graphql_type=graphql_type,
            pagination=default_pagination,
            order=order if isinstance(order, type) else FieldSet(order),
            distinct_on=distinct_on if isinstance(distinct_on, type) else FieldSet(distinct_on),
            paginate=FieldSet(paginate),
            scope=dto_config.scope if declared else None,
            model=model,
            scope_key=None if dto_config.exclude_from_scope else scope_key,
        )
        path_name = (
            "".join(node.value.name for node in current_node.path_from_root()) if current_node is not None else None
        )
        if not declared and type_info.name in self._declared_names[graphql_type]:
            if path_name is None or path_name in self._declared_names[graphql_type]:
                path_name = self._displaced_name(graphql_type, type_info.name)
            type_info = dataclasses.replace(type_info, name=path_name)
        elif self._name_clash(type_info) and path_name is not None:
            type_info = dataclasses.replace(type_info, name=path_name)
        elif path_name is not None:
            self._path_names[type_info] = path_name
        return type_info

    def _displaced_name(self, graphql_type: GraphQLType, name: str) -> str:
        """Return the name generated types take when a declaration owns `name`, the same for every one of them."""
        key = (graphql_type, name)
        if key not in self._displaced_names:
            self._displaced_names[key] = self.uniquify_name(graphql_type, name)
        return self._displaced_names[key]

    def _displace(self, graphql_type: GraphQLType, name: str) -> None:
        """Rename the generated type registered under `name`, so that a declaration can take it."""
        info = self._names_map[graphql_type].get(name)
        if info is None or info in self._declared:
            return
        path_name = self._path_names.get(info)
        if path_name is None or self.get(graphql_type, path_name) is not None:
            path_name = self._displaced_name(graphql_type, name)
        new_info = dataclasses.replace(info, name=path_name)
        type_ = self._type_map.pop(info)
        del self._names_map[graphql_type][name]
        del self.namespace(graphql_type)[name]
        self._type_map[new_info] = type_
        self._names_map[graphql_type][new_info.name] = new_info
        self.namespace(graphql_type)[new_info.name] = type_
        type_.__strawberry_definition__.name = new_info.name
        self._displaced_names.update(
            {
                key: new_info.name
                for key, displaced in self._displaced_names.items()
                if (key[0], displaced) == (graphql_type, name)
            }
        )
        tracked_names = self._tracked_type_names[graphql_type]
        if name in tracked_names:
            tracked_names.remove(name)
            tracked_names.add(new_info.name)
        # Only references to the displaced type follow it: a forward ref by name means the declaration taking it.
        references = self._forward_type_refs[graphql_type][name]
        self._forward_type_refs[graphql_type][new_info.name].extend(ref for ref in references if ref.target is type_)
        references[:] = [ref for ref in references if ref.target is not type_]

    def uniquify_name(self, graphql_type: GraphQLType, name: str) -> str:
        """Return a type name guaranteed to be unique within the registry."""
        while self.get(graphql_type, name):
            self._unique_names[name] += 1
            name = f"{name}{self._unique_names[name]}"
        return name

    def get(self, graphql_type: GraphQLType, name: str) -> RegistryTypeInfo | None:
        return self._names_map[graphql_type].get(name)

    def namespace(self, graphql_type: GraphQLType) -> dict[str, type[Any]]:
        return self._namespaces[graphql_type]

    def register_type(
        self,
        dto: type[StrawchemyDTOT],
        *,
        graphql_type: GraphQLType,
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, Any], None] | None = None,
        declared: bool = False,
        paginate: FieldSpec | None = None,
        order: FieldSpec | type[OrderByDTO] | None = None,
        distinct_on: FieldSpec | type[EnumDTO] | None = None,
        default_pagination: DefaultOffsetPagination | None = None,
        default_name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        scope_key: Hashable | None = None,
    ) -> type[StrawchemyDTOT]:
        type_info = self._type_info(
            dto=dto,
            graphql_type=graphql_type,
            dto_config=dto_config,
            current_node=current_node,
            paginate=paginate,
            order=order,
            distinct_on=distinct_on,
            default_pagination=default_pagination,
            default_name=default_name,
            declared=declared,
            scope_key=scope_key,
        )
        self._claim(type_info, dto, declared=declared)
        if "__strawberry_definition__" in vars(dto):
            return dto
        if existing := self._type_map.get(type_info):
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
        definition = get_object_definition(strawberry_type, strict=True)
        # The user class inheriting an interface exposes its definition too, so strawberry lists the interface twice.
        definition.interfaces = list({id(interface): interface for interface in definition.interfaces}.values())
        self._register(type_info, strawberry_type)
        return strawberry_type

    def register_enum(
        self,
        enum_type: type[EnumT],
        *,
        dto_config: DTOConfig,
        declared: bool = False,
        default_name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] = (),
        scope_key: Hashable | None = None,
    ) -> type[EnumT]:
        if enum_type in self.namespace("enum").values():
            return enum_type
        type_info = self._type_info(
            dto=enum_type,
            graphql_type="enum",
            dto_config=dto_config,
            default_name=default_name,
            current_node=None,
            declared=declared,
            scope_key=scope_key,
        )
        self._claim(type_info, enum_type, declared=declared)
        if existing := self._type_map.get(type_info):
            return cast("type[EnumT]", existing)

        strawberry_type = strawberry.enum(
            cls=enum_type, name=type_info.name, description=description, directives=directives
        )
        self._register(type_info, strawberry_type)
        return strawberry_type
