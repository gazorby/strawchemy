"""Data Transfer Object (DTO) classes for dataclasses.

This module defines base classes and utilities for working with DTOs that
are based on Python dataclasses. It provides a way to map data between
dataclasses and other data models, such as SQLAlchemy models.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from inspect import getmodule
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias, TypeVar, override

from strawchemy.dto.base import DTOBackend, DTOBase, MappedDTO, ModelFieldT, ModelT
from strawchemy.dto.types import DTO_MISSING, DTOMissingType

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from strawchemy.dto.base import DTOFieldDefinition

__all__ = ("DataclassDTO", "DataclassDTOBackend", "DataclassDTOT", "MappedDataclassDTO")

DataclassDTOT = TypeVar("DataclassDTOT", bound="DataclassDTO[Any] | MappedDataclassDTO[Any]")


class DataclassDTO(DTOBase[ModelT]): ...


class BasicFieldInfo(NamedTuple):
    name: str
    type: Any


class FullFieldInfo(NamedTuple):
    name: str
    type: Any
    field: dataclasses.Field[Any]


DataclassFieldInfo: TypeAlias = BasicFieldInfo | FullFieldInfo


@dataclass
class MappedDataclassDTO(MappedDTO[ModelT]): ...


class DataclassDTOBackend(DTOBackend[DataclassDTOT]):
    def __init__(self, dto_base: type[DataclassDTOT]) -> None:
        self.dto_base = dto_base

    def _construct_field_info(self, field_def: DTOFieldDefinition[ModelT, ModelFieldT]) -> DataclassFieldInfo:
        if not isinstance(field_def.default_factory, DTOMissingType):
            return FullFieldInfo(
                field_def.name, field_def.type_, dataclasses.field(default_factory=field_def.default_factory)
            )
        if not isinstance(field_def.default, DTOMissingType):
            return FullFieldInfo(field_def.name, field_def.type_, dataclasses.field(default=field_def.default))

        return BasicFieldInfo(field_def.name, field_def.type_)

    @override
    def build(
        self,
        name: str,
        model: type[Any],
        field_definitions: Iterable[DTOFieldDefinition[Any, ModelFieldT]],
        base: type[Any] | None = None,
        repr: bool = True,
        eq: bool = True,
        order: bool = False,
        unsafe_hash: bool = False,
        frozen: bool = False,
        match_args: bool = True,
        kw_only: bool = True,
        slots: bool = False,
        **kwargs: Any,
    ) -> type[DataclassDTOT]:
        namespace: dict[str, Any] = {}
        fields: list[DataclassFieldInfo] = []
        post_init_validator: list[Callable[[DataclassDTOT], None]] = []

        for field in field_definitions:
            field_info = self._construct_field_info(field)
            fields.append(field_info)

            if field.purpose_config.validator is not None:

                def _validator(
                    self: DataclassDTOT,
                    _name: str = field.name,
                    _validator_function: Callable[[Any], Any] = field.purpose_config.validator,
                ) -> None:
                    value = getattr(self, _name)
                    if value is not DTO_MISSING:
                        return setattr(self, _name, _validator_function(value))
                    return setattr(self, _name, _validator_function(value))

                post_init_validator.append(_validator)

        if post_init_validator:

            def post_init(
                self: DataclassDTOT, _validators: list[Callable[[DataclassDTOT], None]] = post_init_validator
            ) -> None:
                for validator in _validators:
                    validator(self)

            namespace["__post_init__"] = post_init

        module = __name__
        if model_module := getmodule(model):
            module = model_module.__name__

        bases = (self.dto_base, base) if base else (self.dto_base,)

        return dataclasses.make_dataclass(
            name,
            fields=fields,
            bases=bases,
            module=module,
            repr=repr,
            eq=eq,
            order=order,
            unsafe_hash=unsafe_hash,
            frozen=frozen,
            match_args=match_args,
            kw_only=kw_only,
            slots=slots,
            namespace=namespace,
        )
