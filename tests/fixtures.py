from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from strawchemy.mapper import Strawchemy

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from tests.utils import sqlalchemy_dataclass_factory, sqlalchemy_pydantic_factory

if TYPE_CHECKING:
    from tests.typing import MappedDataclassFactory, MappedPydanticFactory

__all__ = ("sqlalchemy_dataclass_factory", "sqlalchemy_pydantic_factory", "strawchemy")


@pytest.fixture
def strawchemy() -> Strawchemy[DeclarativeBase, QueryableAttribute[Any]]:
    return Strawchemy()


@pytest.fixture(name="sqlalchemy_dataclass_factory")
def fx_sqlalchemy_dataclass_factory() -> MappedDataclassFactory:
    return sqlalchemy_dataclass_factory()


@pytest.fixture(name="sqlalchemy_pydantic_factory")
def fx_sqlalchemy_pydantic_factory() -> MappedPydanticFactory:
    return sqlalchemy_pydantic_factory()
