from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ForwardRef, TypeVar, cast, get_args, get_origin

import strawberry
from strawberry.scalars import JSON  # noqa: TC001
from strawberry.types import get_object_definition, has_object_definition
from strawchemy.graphql.filters import GeoComparison
from strawchemy.strawberry import pydantic as strawberry_pydantic

from ._utils import strawberry_inner_type, strawberry_type_from_pydantic

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawberry.types.field import StrawberryField
    from strawchemy.graphql.filters import AnyGraphQLComparison
    from strawchemy.strawberry.typing import StrawchemyTypeWithStrawberryObjectDefinition

    from .typing import GraphQLType


__all__ = ("RegistryTypeInfo", "StrawberryRegistry")

EnumT = TypeVar("EnumT", bound=Enum)


class _StrawberryGeoComparison:
    contains_geometry: JSON | None = strawberry.UNSET
    within_geometry: JSON | None = strawberry.UNSET


@dataclass(frozen=True, eq=True)
class RegistryTypeInfo:
    name: str
    graphql_type: GraphQLType
    user_defined: bool
    override: bool


class StrawberryRegistry:
    def __init__(self) -> None:
        self._strawberry_object_types: dict[str, type[StrawchemyTypeWithStrawberryObjectDefinition]] = {}
        self._strawberry_input_types: dict[str, type[StrawberryTypeFromPydantic[Any]]] = {}
        self._strawberry_interface_types: dict[str, type[StrawchemyTypeWithStrawberryObjectDefinition]] = {}
        self._strawberry_enums: dict[str, type[Enum]] = {}
        self._field_map: defaultdict[str, list[StrawberryField]] = defaultdict(list)
        self._type_infos: set[RegistryTypeInfo] = set()

    def conflicts(self, type_info: RegistryTypeInfo) -> bool:
        # Type conflict if:
        # - A user defined type with the same name, that is not marked as override already exists
        return dataclasses.replace(type_info, user_defined=True, override=False) in self._type_infos

    def _update_annotation_namespace(
        self,
        strawberry_type: type[WithStrawberryObjectDefinition | StrawberryTypeFromPydantic[PydanticModel]],
        graphql_type: GraphQLType,
    ) -> None:
        object_definition = get_object_definition(strawberry_type, strict=True)
        for field in object_definition.fields:
            field_type_name: str | None = None
            if field_type_def := get_object_definition(strawberry_inner_type(field.type)):
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
                self._field_map[field_type_name].append(field)

    def _register_type(
        self, type_name: str, strawberry_type: type[Any], graphql_type: GraphQLType, override: bool, user_defined: bool
    ) -> None:
        self.namespace(graphql_type)[type_name] = strawberry_type
        if override:
            for field in self._field_map[type_name]:
                field.type = strawberry_type
        self._update_annotation_namespace(strawberry_type, graphql_type)
        self._type_infos.add(RegistryTypeInfo(type_name, graphql_type, user_defined, override))

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
        return tuple(cls._inner_types(t)[0] for t in get_args(typ))

    def namespace(self, graphql_type: GraphQLType) -> dict[str, type[Any]]:
        if graphql_type == "object":
            return self._strawberry_object_types
        if graphql_type == "input":
            return self._strawberry_input_types
        return self._strawberry_interface_types

    def register_dataclass(
        self,
        type_: type[Any],
        name: str,
        graphql_type: GraphQLType,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
    ) -> type[Any]:
        type_name = name or type_.__name__

        if has_object_definition(type_):
            return type_
        if not override and (existing := self.namespace(graphql_type).get(type_name)):
            return existing

        strawberry_type = strawberry.type(
            type_,
            name=type_name,
            is_input=graphql_type == "input",
            is_interface=graphql_type == "interface",
            description=description,
            directives=directives,
        )
        self._register_type(type_name, strawberry_type, graphql_type, override, user_defined)
        return strawberry_type

    def register_pydantic(
        self,
        pydantic_type: type[PydanticModel],
        name: str,
        graphql_type: GraphQLType,
        all_fields: bool = True,
        fields: list[str] | None = None,
        partial: bool = False,
        partial_fields: set[str] | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        use_pydantic_alias: bool = True,
        base: type[Any] | None = None,
        override: bool = False,
        user_defined: bool = False,
    ) -> type[StrawberryTypeFromPydantic[PydanticModel]]:
        type_name = name or pydantic_type.__name__
        strawberry_attr = "_strawberry_input_type" if graphql_type == "input" else "_strawberry_type"

        if existing := strawberry_type_from_pydantic(pydantic_type):
            return existing
        if not override and (existing := self.namespace(graphql_type).get(type_name)):
            setattr(pydantic_type, strawberry_attr, existing)
            return existing

        base = base if base is not None else type(type_name, (), {})

        strawberry_type = strawberry_pydantic.type(
            pydantic_type,
            is_input=graphql_type == "input",
            is_interface=graphql_type == "interface",
            all_fields=all_fields,
            fields=fields,
            partial=partial,
            name=type_name,
            description=description,
            directives=directives,
            use_pydantic_alias=use_pydantic_alias,
            partial_fields=partial_fields,
        )(base)
        self._register_type(type_name, strawberry_type, graphql_type, override, user_defined)
        return strawberry_type

    def register_enum(
        self,
        enum_type: type[EnumT],
        name: str | None = None,
        description: str | None = None,
        directives: Iterable[object] = (),
    ) -> type[EnumT]:
        type_name = name or f"{enum_type.__name__}Enum"
        if existing := self._strawberry_enums.get(type_name):
            return cast(type[EnumT], existing)
        strawberry_enum_type = strawberry.enum(cls=enum_type, name=name, description=description, directives=directives)
        self._strawberry_enums[type_name] = strawberry_enum_type
        return strawberry_enum_type

    def register_comparison_type(
        self, comparison_type: type[AnyGraphQLComparison]
    ) -> type[StrawberryTypeFromPydantic[AnyGraphQLComparison]]:
        if issubclass(comparison_type, GeoComparison):
            return self.register_pydantic(
                pydantic_type=comparison_type,
                name=comparison_type.field_type_name(),
                graphql_type="input",
                partial=True,
                all_fields=False,
                base=_StrawberryGeoComparison,
            )

        return self.register_pydantic(
            pydantic_type=comparison_type,
            name=comparison_type.field_type_name(),
            description=comparison_type.field_description(),
            graphql_type="input",
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
        self._strawberry_object_types.clear()
        self._strawberry_input_types.clear()
        self._strawberry_interface_types.clear()
        self._strawberry_enums.clear()
        self._field_map.clear()
        self._type_infos.clear()
