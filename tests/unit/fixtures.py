from __future__ import annotations

from typing import Any

import pytest
from strawchemy.dto.backend.dataclass import DataclassDTOBackend, MappedDataclassDTO
from strawchemy.dto.base import DTOFactory
from strawchemy.mapper import Strawchemy
from strawchemy.sqlalchemy.inspector import SQLAlchemyInspector

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute


@pytest.fixture
def strawchemy() -> Strawchemy[DeclarativeBase, QueryableAttribute[Any]]:
    return Strawchemy()


@pytest.fixture
def sqlalchemy_dataclass_factory() -> DTOFactory[
    DeclarativeBase, QueryableAttribute[Any], MappedDataclassDTO[DeclarativeBase]
]:
    return DTOFactory(SQLAlchemyInspector(), DataclassDTOBackend(MappedDataclassDTO))
