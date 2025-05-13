from __future__ import annotations

from dataclasses import dataclass
from inspect import getmodule
from types import new_class
from typing import TYPE_CHECKING, Any, TypeVar, get_origin, override

import strawberry
from strawberry.types.field import StrawberryField
from strawchemy.dto.base import DTOBackend, DTOBase, MappedDTO, ModelFieldT, ModelT
from strawchemy.dto.types import DTO_MISSING, DTOMissingType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from strawchemy.dto.base import DTOFieldDefinition

__all__ = ("AnnotatedDTOT", "StrawberrryDTOBackend", "StrawberryDTO", "StrawberryDTO")

AnnotatedDTOT = TypeVar("AnnotatedDTOT", bound="StrawberryDTO[Any] | MappedStrawberryDTO[Any]")


class StrawberryDTO(DTOBase[ModelT]): ...


class MappedStrawberryDTO(MappedDTO[ModelT]): ...


@dataclass
class FieldInfo:
    name: str
    type: Any
    field: StrawberryField | DTOMissingType = DTO_MISSING


class StrawberrryDTOBackend(DTOBackend[AnnotatedDTOT]):
    def __init__(self, dto_base: type[AnnotatedDTOT]) -> None:
        self.dto_base = dto_base
        base_cls = origin if (origin := get_origin(dto_base)) else dto_base
        self._base_annotations = {
            name: value for name, value in base_cls.__annotations__.items() if not self._is_private_attribute(name)
        }

    def _construct_field_info(self, field_def: DTOFieldDefinition[ModelT, ModelFieldT]) -> FieldInfo:
        strawberry_field: StrawberryField | None = None
        if not isinstance(field_def.default_factory, DTOMissingType):
            if isinstance(field_def.default_factory(), list | tuple):
                strawberry_field = strawberry.field(default_factory=list)
            else:
                strawberry_field = strawberry.field(default=strawberry.UNSET)
        if not isinstance(field_def.default, DTOMissingType):
            strawberry_field = strawberry.field(default=field_def.default)
        if strawberry_field:
            return FieldInfo(field_def.name, field_def.type_, strawberry_field)
        return FieldInfo(field_def.name, field_def.type_)

    @classmethod
    def _is_private_attribute(cls, name: str) -> bool:
        return name.startswith(("__strawchemy", "__dto"))

    @override
    def copy(self, dto: type[AnnotatedDTOT], name: str) -> type[AnnotatedDTOT]:
        annotations = dto.__annotations__
        attributes = {name: getattr(dto, name) for name in annotations if hasattr(dto, name)}
        attributes |= {
            name: value
            for name, value in dto.__dict__.items()
            if isinstance(value, StrawberryField) or self._is_private_attribute(name)
        }

        def _exec_body(namespace: dict[str, Any]) -> dict[str, Any]:
            namespace["__module__"] = dto.__module__
            namespace["__annotations__"] = annotations
            namespace.update(attributes)
            return namespace

        return new_class(name, (self.dto_base,), exec_body=_exec_body)

    @override
    def build(
        self,
        name: str,
        model: type[Any],
        field_definitions: Iterable[DTOFieldDefinition[Any, ModelFieldT]],
        base: type[Any] | None = None,
        **kwargs: Any,
    ) -> type[AnnotatedDTOT]:
        fields: list[FieldInfo] = []
        dto_field_definitions: dict[str, DTOFieldDefinition[Any, ModelFieldT]] = {}

        for field in field_definitions:
            dto_field_definitions[field.name] = field
            fields.append(self._construct_field_info(field))

        module = __name__
        if model_module := getmodule(self.dto_base):
            module = model_module.__name__

        bases = (base, self.dto_base) if base else (self.dto_base,)

        annotations = self._base_annotations | {field.name: field.type for field in fields}
        attributes = {field.name: field.field for field in fields if field.field is not DTO_MISSING}
        base_attributes = {
            name: getattr(self.dto_base, name) for name in self._base_annotations if hasattr(self.dto_base, name)
        }
        doc = f"DTO generated to be decorated by strawberry for {model.__name__} model"
        if base:
            annotations |= base.__annotations__
            attributes |= {name: value for name, value in base.__dict__.items() if isinstance(value, StrawberryField)}
            doc = base.__doc__ or doc

        def _exec_body(namespace: dict[str, Any]) -> dict[str, Any]:
            namespace["__module__"] = module
            namespace["__doc__"] = doc
            namespace["__annotations__"] = annotations
            namespace["__dto_field_definitions__"] = dto_field_definitions
            namespace["__dto_model__"] = model
            namespace.update(base_attributes | attributes)
            return namespace

        return new_class(name, bases=bases, exec_body=_exec_body)
