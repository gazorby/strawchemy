"""Pydantic DTO implementation.

This module provides classes and utilities for creating Data Transfer Objects (DTOs)
using Pydantic. It includes base classes for Pydantic DTOs, a backend class
for generating DTOs from models, and support for mapping DTOs to SQLAlchemy models.
"""

from __future__ import annotations

from inspect import getmodule
from typing import TYPE_CHECKING, Annotated, Any, TypeVar, override

from pydantic import BaseModel, BeforeValidator, ConfigDict, create_model
from pydantic.fields import Field, FieldInfo

from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, MappedDTO, ModelFieldT, ModelT
from strawchemy.dto.types import DTO_MISSING, DTOMissingType

if TYPE_CHECKING:
    from collections.abc import Iterable


__all__ = ("MappedPydanticDTO", "PydanticDTO", "PydanticDTOBackend")


PydanticDTOT = TypeVar("PydanticDTOT", bound="PydanticDTO[Any] | MappedPydanticDTO[Any]")


class _PydanticDTOBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True, populate_by_name=True)


class PydanticDTO(_PydanticDTOBase, DTOBase[ModelT]): ...


class MappedPydanticDTO(_PydanticDTOBase, MappedDTO[ModelT]): ...


class PydanticDTOBackend(DTOBackend[PydanticDTOT]):
    """Implements DTO factory using pydantic."""

    def __init__(self, dto_base: type[PydanticDTOT]) -> None:
        self.dto_base = dto_base

    def _construct_field_info(self, field_def: DTOFieldDefinition[ModelT, ModelFieldT]) -> FieldInfo:
        """Build a `FieldInfo instance reflecting the given field_def."""
        kwargs: dict[str, Any] = {}
        if field_def.required:
            kwargs["default"] = ...
        elif not isinstance(field_def.default_factory, DTOMissingType):
            kwargs["default_factory"] = field_def.default_factory
        elif not isinstance(field_def.default, DTOMissingType):
            kwargs["default"] = field_def.default
        if field_def.purpose_config.alias:
            kwargs["alias"] = field_def.model_field_name
        return Field(**kwargs)

    @override
    def update_forward_refs(self, dto: type[PydanticDTOT], namespace: dict[str, type[PydanticDTOT]]) -> None | bool:
        dto.model_rebuild(_types_namespace=namespace, raise_errors=False)

    @override
    def build(
        self,
        name: str,
        model: type[ModelT],
        field_definitions: Iterable[DTOFieldDefinition[ModelT, ModelFieldT]],
        base: type[Any] | None = None,
        config_dict: ConfigDict | None = None,
        docstring: bool = True,
        **kwargs: Any,
    ) -> type[PydanticDTOT]:
        fields: dict[str, tuple[Any, FieldInfo]] = {}
        base_annotations = base.__annotations__ if base else {}

        for field_def in field_definitions:
            field_type = field_def.type_
            validator: BeforeValidator | None = None
            if field_def.purpose_config.validator:
                validator = BeforeValidator(field_def.purpose_config.validator)
            if validator:
                field_type = Annotated[field_type, validator]
            fields[field_def.name] = (field_type, self._construct_field_info(field_def))

        # Copy fields from base to avoid Pydantic warning about shadowing fields
        for f_name in base_annotations:
            field_info: FieldInfo = Field()
            attribute = getattr(base, f_name, DTO_MISSING)
            if not isinstance(attribute, DTOMissingType):
                field_info = attribute if isinstance(attribute, FieldInfo) else Field(default=attribute)
            field_type = fields[f_name][0] if f_name in fields else base_annotations[f_name]
            fields[f_name] = (field_type, field_info)

        module = __name__
        if model_module := getmodule(model):
            module = model_module.__name__

        dto = create_model(
            name,
            __base__=(self.dto_base,),
            __config__=None,
            __module__=module,
            __validators__=None,
            __doc__=f"Pydantic generated DTO for {model.__name__} model" if docstring else None,
            __cls_kwargs__=None,
            **fields,
        )

        if config_dict:
            cls_body = {"model_config": config_dict} if config_dict else {}
            return type(dto.__name__, (dto,), cls_body)
        return dto
