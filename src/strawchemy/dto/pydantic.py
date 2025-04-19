from __future__ import annotations

from typing import Any

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute

from .backend.pydantic import MappedPydanticDTO, PydanticDTOBackend
from .base import DTOFactory
from .inspectors.sqlalchemy import SQLAlchemyInspector

__all__ = ("factory", "pydantic_dto")

_inspector = SQLAlchemyInspector()
_TypedFactory = DTOFactory[DeclarativeBase, QueryableAttribute[Any], MappedPydanticDTO[Any]]

factory = _TypedFactory(_inspector, PydanticDTOBackend(MappedPydanticDTO))
pydantic_dto = factory.decorator
