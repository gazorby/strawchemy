from __future__ import annotations

import dataclasses
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ForwardRef, Literal, NewType, TypeVar, cast, get_args, get_origin, overload

import strawberry
from strawberry.annotation import StrawberryAnnotation
from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.base import StrawberryContainer
from strawberry.types.field import StrawberryField
from strawchemy.strawberry import pydantic as strawberry_pydantic

from ._utils import strawberry_contained_types, strawchemy_type_from_pydantic

try:
    from strawchemy.graphql.filters.geo import GeoComparison

    geo_comparison = GeoComparison
except ModuleNotFoundError:  # pragma: no cover
    geo_comparison = None

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.types.arguments import StrawberryArgument
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawchemy.graphql.filters import AnyGraphQLComparison
    from strawchemy.strawberry.typing import StrawchemyTypeWithStrawberryObjectDefinition
    from strawchemy.types import DefaultOffsetPagination

    from .typing import GraphQLType


__all__ = ("RegistryTypeInfo", "StrawberryRegistry")

T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)

_RegistryMissing = NewType("_RegistryMissing", object)


@dataclass
class _TypeReference:
    ref_holder: StrawberryField | StrawberryArgument

    @classmethod
    def _replace_contained_type(
        cls, container: StrawberryContainer, strawberry_type: type[WithStrawberryObjectDefinition]
    ) -> StrawberryContainer:
        container_copy = copy(container)
        if isinstance(container.of_type, StrawberryContainer):
            replaced = cls._replace_contained_type(container.of_type, strawberry_type)
        else:
            replaced = strawberry_type
        container_copy.of_type = replaced
        return container_copy

    def _set_type(self, strawberry_type: type[WithStrawberryObjectDefinition] | StrawberryContainer) -> None:
        if isinstance(self.ref_holder, StrawberryField):
            self.ref_holder.type = strawberry_type
        self.ref_holder.type_annotation = StrawberryAnnotation(strawberry_type)

    def update_type(self, strawberry_type: type[WithStrawberryObjectDefinition]) -> None:
        if isinstance(self.ref_holder.type, StrawberryContainer):
            self._set_type(self._replace_contained_type(self.ref_holder.type, strawberry_type))
        else:
            self._set_type(strawberry_type)


@dataclass(frozen=True, eq=True)
class RegistryTypeInfo:
    name: str
    graphql_type: GraphQLType
    user_defined: bool = False
    override: bool = False
    pagination: DefaultOffsetPagination | Literal[False] = False
    order_by: bool = False


class StrawberryRegistry:
    def __init__(self) -> None:
        self._namespaces: defaultdict[GraphQLType, dict[str, type[StrawchemyTypeWithStrawberryObjectDefinition]]] = (
            defaultdict(dict)
        )
        self._type_references: defaultdict[GraphQLType, defaultdict[str, list[_TypeReference]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._type_map: dict[RegistryTypeInfo, type[Any]] = {}
        self._names_map: defaultdict[GraphQLType, dict[str, RegistryTypeInfo]] = defaultdict(dict)
        self._tracked_type_names: defaultdict[GraphQLType, set[str]] = defaultdict(set)

    def _update_references(self, field: StrawberryField | StrawberryArgument, graphql_type: GraphQLType) -> None:
        field_type_name: str | None = None
        for inner_type in strawberry_contained_types(field.type):
            if field_type_def := get_object_definition(inner_type):
                field_type_name = field_type_def.name
            if field.type_annotation:
                for type_ in self._inner_types(field.type_annotation.raw_annotation):
                    if isinstance(type_, ForwardRef):
                        field_type_name = type_.__forward_arg__
                    elif isinstance(type_, str):
                        field_type_name = type_
                    else:
                        continue
                    field.type_annotation.namespace = self.namespace(graphql_type)
            if field_type_name:
                type_info = self.get(graphql_type, field_type_name, None)
                if type_info is None or not type_info.override:
                    self._type_references[graphql_type][field_type_name].append(_TypeReference(field))
                else:
                    _TypeReference(field).update_type(self._type_map[type_info])
            if field_type_def:
                self._track_references(inner_type, graphql_type)

    def _track_references(
        self,
        strawberry_type: type[WithStrawberryObjectDefinition | StrawberryTypeFromPydantic[PydanticModel]],
        graphql_type: GraphQLType,
        force: bool = False,
    ) -> None:
        object_definition = get_object_definition(strawberry_type, strict=True)
        if not force and object_definition.name in self._tracked_type_names[graphql_type]:
            return
        self._tracked_type_names[graphql_type].add(object_definition.name)
        for field in object_definition.fields:
            for argument in field.arguments:
                if any(
                    get_object_definition(inner_type) is not None
                    for inner_type in strawberry_contained_types(argument.type)
                ):
                    self._update_references(argument, "input")
            self._update_references(field, graphql_type)

    def _register_type(self, type_info: RegistryTypeInfo, strawberry_type: type[Any]) -> None:
        self.namespace(type_info.graphql_type)[type_info.name] = strawberry_type
        if type_info.override:
            for reference in self._type_references[type_info.graphql_type][type_info.name]:
                reference.update_type(strawberry_type)
        self._track_references(strawberry_type, type_info.graphql_type, force=type_info.override)
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
        if (existing := self.get(type_info.graphql_type, type_info.name, None)) and existing.override:
            return self._type_map[existing]
        if not type_info.override and (existing := self._type_map.get(type_info)):
            return existing
        return None

    def _check_conflicts(self, type_info: RegistryTypeInfo) -> None:
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
        # return type_info.name in self.namespace(type_info.graphql_type) and
        return dataclasses.replace(type_info, user_defined=True, override=False) in self or (
            dataclasses.replace(type_info, user_defined=False, override=False) in self
            and not type_info.override
            and type_info.user_defined
        )

    def namespace(self, graphql_type: GraphQLType) -> dict[str, type[Any]]:
        return self._namespaces[graphql_type]

    def register_dataclass(
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

    def register_pydantic(
        self,
        pydantic_type: type[PydanticModel],
        type_info: RegistryTypeInfo,
        all_fields: bool = True,
        fields: list[str] | None = None,
        partial: bool = False,
        partial_fields: set[str] | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        use_pydantic_alias: bool = True,
        base: type[Any] | None = None,
    ) -> type[StrawberryTypeFromPydantic[PydanticModel]]:
        self._check_conflicts(type_info)
        strawberry_attr = "_strawberry_input_type" if type_info.graphql_type == "input" else "_strawberry_type"
        if existing := strawchemy_type_from_pydantic(pydantic_type):
            return existing
        if existing := self._get(type_info):
            setattr(pydantic_type, strawberry_attr, existing)
            return existing

        base = base if base is not None else type(type_info.name, (), {})

        strawberry_type = strawberry_pydantic.type(
            pydantic_type,
            is_input=type_info.graphql_type == "input",
            is_interface=type_info.graphql_type == "interface",
            all_fields=all_fields,
            fields=fields,
            partial=partial,
            name=type_info.name,
            description=description,
            directives=directives,
            use_pydantic_alias=use_pydantic_alias,
            partial_fields=partial_fields,
        )(base)
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
            return cast(type[EnumT], existing)
        strawberry_enum_type = strawberry.enum(cls=enum_type, name=name, description=description, directives=directives)
        self.namespace("enum")[type_name] = strawberry_enum_type
        return strawberry_enum_type

    def register_comparison_type(
        self, comparison_type: type[AnyGraphQLComparison]
    ) -> type[StrawberryTypeFromPydantic[AnyGraphQLComparison]]:
        type_info = RegistryTypeInfo(name=comparison_type.comparison_type_name(), graphql_type="input")
        if geo_comparison is not None and issubclass(comparison_type, geo_comparison):
            from .geo import StrawberryGeoComparison

            return self.register_pydantic(
                comparison_type,
                type_info,
                partial=True,
                all_fields=False,
                base=StrawberryGeoComparison,
            )

        return self.register_pydantic(
            comparison_type,
            type_info,
            description=comparison_type.field_description(),
            partial=True,
        )

    def clear(self) -> None:
        """Clear all registered types in the registry.

        This method removes all registered types, including:
        - Strawberry object types
        - Input types
        - Interface types
        - Enum types

        Note: This is useful when you need to reset the registry to its initial empty state.
        """
        self._namespaces.clear()
        self._type_map.clear()
        self._type_references.clear()
        self._names_map.clear()
