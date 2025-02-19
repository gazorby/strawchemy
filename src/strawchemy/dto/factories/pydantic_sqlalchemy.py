from __future__ import annotations

from typing import Any

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTOBackend
from strawchemy.dto.base import DTOFactory
from strawchemy.dto.inspectors.sqlalchemy import SQLAlchemyInspector

__all__ = ("pydantic_dto",)

_inspector = SQLAlchemyInspector()
_TypedFactory = DTOFactory[DeclarativeBase, QueryableAttribute[Any], MappedPydanticDTO[Any]]

pydantic_dto = _TypedFactory(_inspector, PydanticDTOBackend(MappedPydanticDTO)).decorator
