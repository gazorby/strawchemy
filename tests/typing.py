from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from strawchemy.dto.backend.dataclass import MappedDataclassDTO
    from strawchemy.dto.base import DTOFactory

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute


MappedDataclassFactory: TypeAlias = (
    "DTOFactory[DeclarativeBase, QueryableAttribute[Any], MappedDataclassDTO[DeclarativeBase]]"
)
