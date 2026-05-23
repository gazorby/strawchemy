from __future__ import annotations

from enum import Enum
from inspect import getmodule
from types import new_class
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from typing_extensions import Unpack, override

from strawchemy.dto.base import DTOBackend, DTOBase, DTOFactory, DTOFieldDefinition, Relation
from strawchemy.dto.strawberry import EnumDTO, GraphQLFieldDefinition
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.utils.text import snake_to_lower_camel_case

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from strawchemy import Strawchemy
    from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
    from strawchemy.schema.factories._kwargs import DecoratorKwargs, FactoryMethodKwargs
    from strawchemy.utils.graph import Node

T = TypeVar("T")


class EnumBackend(DTOBackend[EnumDTO]):
    def __init__(self, to_camel: bool = True) -> None:
        self.dto_base = EnumDTO
        self.to_camel = to_camel

    @override
    def build(
        self,
        name: str,
        model: type[DeclarativeBase],
        field_definitions: Iterable[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]],
        base: type[Any] | None = None,
        values: Iterable[Any] | None = None,
        **kwargs: Any,
    ) -> type[EnumDTO]:
        field_map = {
            snake_to_lower_camel_case(field.name) if self.to_camel else field.name: field for field in field_definitions
        }
        values = list(values or []) or field_map.keys()

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
            EnumDTO(value=name, names=list(zip(list(field_map), values, strict=False)), type=base, module=module),
        )

    @override
    @classmethod
    def copy(cls, dto: type[EnumDTO], name: str) -> EnumDTO:  # pyright: ignore[reportIncompatibleMethodOverride]
        enum = EnumDTO(value=name, names=[(value.name, value.value) for value in dto])
        enum.__field_definitions__ = dto.__field_definitions__
        return enum


class UpsertConflictEnumBackend(EnumBackend):
    def __init__(self, inspector: SQLAlchemyGraphQLInspector, to_camel: bool = True) -> None:
        self.dto_base = EnumDTO
        self.to_camel = to_camel
        self._inspector = inspector

    @override
    def build(
        self,
        name: str,
        model: type[DeclarativeBase],
        field_definitions: Iterable[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]],
        base: type[Any] | None = None,
        values: Iterable[Any] | None = None,
        **kwargs: Any,
    ) -> type[EnumDTO]:
        field_definitions = list(field_definitions)
        return super().build(
            name,
            model,
            field_definitions,
            base,
            [field.metadata["constraint"] for field in field_definitions],
            **kwargs,
        )


class EnumFactory(DTOFactory[DeclarativeBase, QueryableAttribute[Any], EnumDTO]):
    inspector: SQLAlchemyGraphQLInspector

    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[EnumDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        self._mapper = mapper
        super().__init__(mapper.config.inspector, backend or EnumBackend(), handle_cycles, type_map)

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
        if_no_fields: Literal["raise", "skip"] = "skip",
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        for field in super().iter_field_definitions(name, model, dto_config, base, node, if_no_fields, **kwargs):
            yield GraphQLFieldDefinition.from_field(field)

    @override
    def decorator(
        self,
        model: type[DeclarativeBase],
        purpose: Purpose = Purpose.READ,
        **kwargs: Unpack[DecoratorKwargs],
    ) -> Callable[[type[Any]], type[EnumDTO]]:
        return super().decorator(model, purpose, **kwargs)

    def input(
        self,
        model: type[DeclarativeBase],
        **kwargs: Unpack[DecoratorKwargs],
    ) -> Callable[[type[Any]], type[EnumDTO]]:
        return super().decorator(model, Purpose.WRITE, **kwargs)

    def upsert_conflict_fields(
        self,
        model: type[DeclarativeBase],
        name: str | None = None,
    ) -> type[Enum]:
        name = name or f"{model.__name__}ConflictFields"
        return cast(
            "type[Enum]",
            Enum(
                name,
                [
                    (f"{'_'.join(col.key for col in constraint.columns)}", constraint)
                    for constraint in self.inspector.unique_constraints(model)
                ],
            ),
        )

    @override
    def factory(
        self,
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[EnumDTO]:
        register_type = kwargs.get("register_type", True)
        dto = super().factory(model=model, dto_config=dto_config, base=base, name=name, **kwargs)
        if register_type:
            return self._mapper.registry.register_enum(
                dto,
                dto_config=dto_config,
                description=kwargs.get("description"),
                directives=kwargs.get("directives") or (),
                override=kwargs.get("override", False),
                user_defined=kwargs.get("user_defined", False),
            )
        return dto
