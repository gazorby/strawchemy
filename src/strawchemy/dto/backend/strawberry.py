from __future__ import annotations

from dataclasses import dataclass
from inspect import getmembers, getmodule
from types import new_class
from typing import TYPE_CHECKING, Any, TypeVar, cast, get_origin

import strawberry
from strawberry.types.field import StrawberryField
from typing_extensions import override

from strawchemy.dto import Purpose
from strawchemy.dto.base import DTOBackend, DTOBase, MappedDTO, ModelFieldT, ModelT
from strawchemy.dto.types import DTOMissing, DTOUnset
from strawchemy.utils.annotation import get_annotations

if TYPE_CHECKING:
    from collections.abc import Iterable

    from strawchemy.dto.base import DTOFieldDefinition
    from strawchemy.dto.types import DTOConfig

__all__ = ("AnnotatedDTOT", "MappedStrawberryDTO", "StrawberrryDTOBackend", "StrawberryDTO", "StrawberryDTO")

AnnotatedDTOT = TypeVar("AnnotatedDTOT", bound="StrawberryDTO[Any] | MappedStrawberryDTO[Any]")


class StrawberryDTO(DTOBase[ModelT]): ...


class MappedStrawberryDTO(MappedDTO[ModelT]): ...


@dataclass
class FieldInfo:
    name: str
    type: Any
    field: StrawberryField | type[DTOMissing] = DTOMissing


class StrawberrryDTOBackend(DTOBackend[AnnotatedDTOT]):
    def __init__(self, dto_base: type[AnnotatedDTOT], auto_is_type_of: bool = False) -> None:
        # Defaults off so only the main backend (output types from `@sc.type`) opts in via
        # config; the filter/order/aggregate backends never auto-generate `is_type_of`.
        self.dto_base = dto_base
        self.auto_is_type_of = auto_is_type_of
        base_cls = origin if (origin := get_origin(dto_base)) else dto_base
        self._base_annotations = {
            name: value for name, value in get_annotations(base_cls).items() if not self._is_private_attribute(name)
        }

    def _construct_field_info(self, field_def: DTOFieldDefinition[ModelT, ModelFieldT]) -> FieldInfo:
        # A field definition may carry a prebuilt strawberry field (e.g. from ``filter_field``);
        # it already encodes the default and any explicit field config, so use it as-is.
        # Local import: dto.strawberry imports this module at top, so a module-level import cycles.
        from strawchemy.dto.strawberry import GraphQLFieldDefinition  # noqa: PLC0415

        if isinstance(field_def, GraphQLFieldDefinition) and field_def.graphql_field is not None:
            return FieldInfo(field_def.name, field_def.type_, field_def.graphql_field)
        strawberry_field: StrawberryField | None = None
        if field_def.default_factory is not DTOMissing:
            if isinstance(field_def.default_factory(), (list, tuple)):
                strawberry_field = strawberry.field(default_factory=list)
            else:
                strawberry_field = strawberry.field(default=strawberry.UNSET)
        if field_def.default is not DTOMissing:
            # DTOUnset marks a database-resolved default (sequence or SQL expression);
            # render it as UNSET so the field is optional in write inputs.
            default = strawberry.UNSET if field_def.default is DTOUnset else field_def.default
            strawberry_field = strawberry.field(default=default)
        if strawberry_field:
            return FieldInfo(field_def.name, field_def.type_, strawberry_field)
        return FieldInfo(field_def.name, field_def.type_)

    @classmethod
    def _is_private_attribute(cls, name: str) -> bool:
        return name.startswith(("__strawchemy", "__dto"))

    @override
    def copy(self, dto: type[AnnotatedDTOT], name: str) -> type[AnnotatedDTOT]:
        annotations = get_annotations(dto)
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

        return cast("type[AnnotatedDTOT]", new_class(name, (self.dto_base,), exec_body=_exec_body))

    @override
    def build(
        self,
        name: str,
        model: type[Any],
        field_definitions: Iterable[DTOFieldDefinition[Any, ModelFieldT]],
        base: type[Any] | None = None,
        dto_config: DTOConfig | None = None,
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
        attributes = {field.name: field.field for field in fields if field.field is not DTOMissing}
        base_attributes = {
            name: getattr(self.dto_base, name) for name in self._base_annotations if hasattr(self.dto_base, name)
        }
        doc = f"DTO generated to be decorated by strawberry for {model.__name__} model"
        if base:
            base_annotations = get_annotations(base)
            annotations |= base_annotations
            for member_name, value in getmembers(base):
                if member_name.startswith("__"):
                    continue
                if isinstance(value, StrawberryField):
                    attributes[member_name] = value
                elif member_name in base_annotations and not callable(value):
                    # Preserve user-written class-body literal defaults (`= True`) over generated ones
                    attributes[member_name] = strawberry.field(default=value)
            doc = base.__doc__ or doc

        def _exec_body(namespace: dict[str, Any]) -> dict[str, Any]:
            namespace["__module__"] = module
            namespace["__doc__"] = doc
            namespace["__annotations__"] = annotations
            namespace["__dto_field_definitions__"] = dto_field_definitions
            namespace["__dto_model__"] = model

            if (
                self.auto_is_type_of
                and dto_config is not None
                and dto_config.purpose is Purpose.READ
                and not (base is not None and hasattr(base, "is_type_of"))
            ):

                def is_type_of(cls: type[Any], obj: Any, _info: Any, _model: type[Any] = model) -> bool:
                    return isinstance(obj, (cls, _model))

                namespace["is_type_of"] = classmethod(is_type_of)
            namespace.update(base_attributes | attributes)
            return namespace

        return cast("type[AnnotatedDTOT]", new_class(name, bases=bases, exec_body=_exec_body))
