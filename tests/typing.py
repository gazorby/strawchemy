from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from strawchemy.dto.backend.dataclass import MappedDataclassDTO
    from strawchemy.dto.backend.pydantic import MappedPydanticDTO
    from strawchemy.dto.base import DTOFactory

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute


MappedDataclassFactory: TypeAlias = "DTOFactory[DeclarativeBase, QueryableAttribute[Any], MappedDataclassDTO[Any]]"
MappedPydanticFactory: TypeAlias = "DTOFactory[DeclarativeBase, QueryableAttribute[Any], MappedPydanticDTO[Any]]"
AnyFactory: TypeAlias = "MappedDataclassFactory | MappedPydanticFactory"
