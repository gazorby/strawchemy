from __future__ import annotations

from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Any, ForwardRef, Literal, TypeVar, cast, get_args, get_origin

import strawberry
from strawberry.types import get_object_definition, has_object_definition
from strawchemy.graphql.filters import GeoComparison
from strawchemy.strawberry import pydantic as strawberry_pydantic

from ._utils import strawberry_type_from_pydantic

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from strawberry.experimental.pydantic.conversion_types import PydanticModel, StrawberryTypeFromPydantic
    from strawberry.scalars import JSON
    from strawberry.types.base import WithStrawberryObjectDefinition
    from strawchemy.graphql.filters import AnyGraphQLComparison


__all__ = ("StrawberryRegistry",)

GraphQLType = Literal["input", "object", "interface"]

EnumT = TypeVar("EnumT", bound=Enum)


class StrawberryRegistry:
    def __init__(self) -> None:
        self._strawberry_object_types: dict[str, type[StrawberryTypeFromPydantic[Any]]] = {}
        self._strawberry_input_types: dict[str, type[StrawberryTypeFromPydantic[Any]]] = {}
        self._strawberry_interface_types: dict[str, type[StrawberryTypeFromPydantic[Any]]] = {}
        self._strawberry_enums: dict[str, type[Enum]] = {}

    def _update_annotation_namespaces(
        self,
        strawberry_type: type[WithStrawberryObjectDefinition | StrawberryTypeFromPydantic[PydanticModel]],
        graphql_type: GraphQLType,
    ) -> None:
        object_definition = get_object_definition(strawberry_type, strict=True)
        for field in object_definition.fields:
            if not field.type_annotation:
                continue
            for type_ in self._inner_types(field.type_annotation.raw_annotation):
                if not isinstance(type_, ForwardRef | str):
                    continue
                field.type_annotation.namespace = self.namespace(graphql_type)

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

    @cached_property
    def _geo_base_override(self) -> type[Any]:
        class StrawberryGeoComparison:
            contains_geometry: JSON | None = strawberry.UNSET
            within_geometry: JSON | None = strawberry.UNSET

        return StrawberryGeoComparison

    def namespace(self, graphql_type: GraphQLType) -> dict[str, type[StrawberryTypeFromPydantic[Any]]]:
        if graphql_type == "object":
            return self._strawberry_object_types
        if graphql_type == "input":
            return self._strawberry_input_types
        return self._strawberry_interface_types

    def register_dataclass(
        self,
        type_: type[Any],
        name: str,
        is_input: bool = False,
        is_interface: bool = False,
        description: str | None = None,
        directives: Sequence[object] | None = (),
    ) -> type[Any]:
        graphql_type: GraphQLType = "object"
        if is_input:
            graphql_type = "input"
        elif is_interface:
            graphql_type = "interface"
        type_name = name if name else type_.__name__

        if has_object_definition(type_):
            return type_
        if existing := self.namespace(graphql_type).get(type_name):
            return existing

        strawberry_type = strawberry.type(
            type_,
            name=type_name,
            is_input=is_input,
            is_interface=is_interface,
            description=description,
            directives=directives,
        )
        self._update_annotation_namespaces(strawberry_type, graphql_type)
        self.namespace(graphql_type)[type_name] = strawberry_type
        return strawberry_type

    def register_pydantic(
        self,
        pydantic_type: type[PydanticModel],
        name: str,
        is_input: bool = False,
        is_interface: bool = False,
        all_fields: bool = True,
        fields: list[str] | None = None,
        partial: bool = False,
        partial_fields: set[str] | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        use_pydantic_alias: bool = True,
        base: type[Any] | None = None,
    ) -> type[StrawberryTypeFromPydantic[PydanticModel]]:
        graphql_type: GraphQLType = "object"
        if is_input:
            graphql_type = "input"
        elif is_interface:
            graphql_type = "interface"
        type_name = name if name else pydantic_type.__name__
        strawberry_attr = "_strawberry_input_type" if is_input else "_strawberry_type"

        if existing := strawberry_type_from_pydantic(pydantic_type):
            return existing
        if existing := self.namespace(graphql_type).get(type_name):
            setattr(pydantic_type, strawberry_attr, existing)
            return existing

        base = base if base is not None else type(type_name, (), {})

        strawberry_type = strawberry_pydantic.type(
            pydantic_type,
            is_input=is_input,
            is_interface=is_interface,
            all_fields=all_fields,
            fields=fields,
            partial=partial,
            name=type_name,
            description=description,
            directives=directives,
            use_pydantic_alias=use_pydantic_alias,
            partial_fields=partial_fields,
        )(base)
        self._update_annotation_namespaces(strawberry_type, graphql_type)
        self.namespace(graphql_type)[type_name] = strawberry_type
        return strawberry_type

    def register_enum(
        self,
        enum_type: type[EnumT],
        name: str | None = None,
        description: str | None = None,
        directives: Iterable[object] = (),
    ) -> type[EnumT]:
        type_name = name if name else f"{enum_type.__name__}Enum"
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
                is_input=True,
                partial=True,
                all_fields=False,
                base=self._geo_base_override,
            )

        return self.register_pydantic(
            pydantic_type=comparison_type,
            name=comparison_type.field_type_name(),
            description=comparison_type.field_description(),
            is_input=True,
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
