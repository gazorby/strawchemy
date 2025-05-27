"""This module defines factories for creating GraphQL DTOs (Data Transfer Objects).

It includes factories for:
- Aggregate DTOs
- Aggregate Filter DTOs
- OrderBy DTOs
- Type DTOs
- Filter DTOs
- Enum DTOs

These factories are used to generate DTOs that are compatible with GraphQL schemas,
allowing for efficient data transfer and filtering in GraphQL queries.
"""

from __future__ import annotations

from collections.abc import Iterable
from inspect import getmodule
from types import new_class
from typing import TYPE_CHECKING, Any, TypeVar, cast, override

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.dto.base import (
    DTOBackend,
    DTOBase,
    DTOFactory,
    DTOFieldDefinition,
    ModelInspector,
    Relation,
)
from strawchemy.dto.types import DTOConfig, ExcludeFields, IncludeFields, Purpose
from strawchemy.strawberry.dto import EnumDTO, GraphQLFieldDefinition
from strawchemy.utils import snake_to_lower_camel_case

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

    from strawchemy.graph import Node

T = TypeVar("T")


class EnumDTOBackend(DTOBackend[EnumDTO]):
    def __init__(self, to_camel: bool = True) -> None:
        self.dto_base = EnumDTO
        self.to_camel = to_camel

    @override
    def build(
        self,
        name: str,
        model: type[T],
        field_definitions: Iterable[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]],
        base: type[Any] | None = None,
        **kwargs: Any,
    ) -> type[EnumDTO]:
        field_map = {
            snake_to_lower_camel_case(field.name) if self.to_camel else field.name: field for field in field_definitions
        }

        def exec_body(namespace: dict[str, Any]) -> Any:
            def to_field_definition(self: EnumDTO) -> DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]:
                return self.__field_definitions__[self.value]

            namespace["field_definition"] = property(to_field_definition)
            namespace["__field_definitions__"] = field_map

        base = new_class(name=f"{name}Base", bases=(DTOBase,), exec_body=exec_body)
        module = __name__
        if model_module := getmodule(model):
            module = model_module.__name__
        return cast(
            "type[EnumDTO]",
            EnumDTO(value=name, names=[(value, value) for value in list(field_map)], type=base, module=module),
        )

    @override
    @classmethod
    def copy(cls, dto: type[EnumDTO], name: str) -> EnumDTO:  # pyright: ignore[reportIncompatibleMethodOverride]
        enum = EnumDTO(value=name, names=[(value.name, value.value) for value in dto])
        enum.__field_definitions__ = dto.__field_definitions__
        return enum


class EnumDTOFactory(DTOFactory[DeclarativeBase, QueryableAttribute[Any], EnumDTO]):
    def __init__(
        self,
        inspector: ModelInspector[Any, QueryableAttribute[Any]],
        backend: DTOBackend[EnumDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(inspector, backend or EnumDTOBackend(), handle_cycles, type_map)

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}Fields"

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, EnumDTO], None],
        has_override: bool,
    ) -> bool:
        return super().should_exclude_field(field, dto_config, node, has_override) or field.is_relation

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, EnumDTO], None],
        raise_if_no_fields: bool = False,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], None, None]:
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            yield GraphQLFieldDefinition.from_field(field)

    @override
    def decorator(
        self,
        model: type[DeclarativeBase],
        purpose: Purpose = Purpose.READ,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[EnumDTO]]:
        return super().decorator(
            model,
            purpose,
            include=include,
            exclude=exclude,
            partial=partial,
            aliases=aliases,
            alias_generator=alias_generator,
            type_map=type_map,
            **kwargs,
        )
