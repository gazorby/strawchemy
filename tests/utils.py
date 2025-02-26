from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol, override

from strawchemy.dto.backend.dataclass import DataclassDTOBackend, MappedDataclassDTO
from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTOBackend
from strawchemy.dto.base import DTOFactory
from strawchemy.sqlalchemy.inspector import SQLAlchemyInspector

from pydantic import BaseModel
from tests.typing import AnyFactory, MappedDataclassFactory, MappedPydanticFactory

if TYPE_CHECKING:
    from collections.abc import Generator

    from strawchemy.typing import DataclassProtocol

__all__ = ("DTOInspect", "sqlalchemy_dataclass_factory", "sqlalchemy_pydantic_factory")


def sqlalchemy_dataclass_factory() -> MappedDataclassFactory:
    return DTOFactory(SQLAlchemyInspector(), DataclassDTOBackend(MappedDataclassDTO))


def sqlalchemy_pydantic_factory() -> MappedPydanticFactory:
    return DTOFactory(SQLAlchemyInspector(), PydanticDTOBackend(MappedPydanticDTO))


def factory_iterator() -> Generator[AnyFactory]:
    for factory in (sqlalchemy_dataclass_factory, sqlalchemy_pydantic_factory):
        yield factory()


class FactoryType(Enum):
    PYDANTIC = auto()
    DATACLASS = auto()


class DTOInspectProtocol(Protocol):
    @classmethod
    def is_class(cls, dto: type[Any]) -> bool: ...

    def has_init_arg(self, dto: type[Any], name: str) -> bool: ...


class DataclassInspect(DTOInspectProtocol):
    @classmethod
    @override
    def is_class(cls, dto: type[Any]) -> bool:
        return dataclasses.is_dataclass(dto)

    @override
    def has_init_arg(self, dto: type[DataclassProtocol], name: str) -> bool:
        return name in {field.name for field in dataclasses.fields(dto) if field.init}


class PydanticInspect(DTOInspectProtocol):
    @classmethod
    @override
    def is_class(cls, dto: type[Any]) -> bool:
        return issubclass(dto, BaseModel)

    @override
    def has_init_arg(self, dto: type[BaseModel], name: str) -> bool:
        return bool((field := dto.model_fields.get(name)) and field.is_required())


@dataclass
class DTOInspect:
    dto: type[Any]
    inspectors: list[type[DTOInspectProtocol]] = dataclasses.field(
        default_factory=lambda: [DataclassInspect, PydanticInspect]
    )
    inspect: DTOInspectProtocol = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        for inspector in self.inspectors:
            if inspector.is_class(self.dto):
                self.inspect = inspector()
                break
        else:
            msg = f"Unknown dto type: {self.dto}"
            raise TypeError(msg)

    def has_init_arg(self, name: str) -> bool:
        return self.inspect.has_init_arg(self.dto, name)
