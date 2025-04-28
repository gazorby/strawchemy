from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from strawchemy.mapper import Strawchemy

import strawberry
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.amber import AmberSnapshotExtension
from tests.utils import sqlalchemy_dataclass_factory, sqlalchemy_pydantic_factory

from .syrupy import GraphQLFileExtension

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion
    from tests.typing import MappedDataclassFactory, MappedPydanticFactory

__all__ = ("sqlalchemy_dataclass_factory", "sqlalchemy_pydantic_factory", "strawchemy")


@pytest.fixture
def graphql_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.use_extension(GraphQLFileExtension)


@pytest.fixture
def sql_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.use_extension(AmberSnapshotExtension)


@pytest.fixture
def strawchemy() -> Strawchemy:
    return Strawchemy()


@pytest.fixture(name="sqlalchemy_dataclass_factory")
def fx_sqlalchemy_dataclass_factory() -> MappedDataclassFactory:
    return sqlalchemy_dataclass_factory()


@pytest.fixture(name="sqlalchemy_pydantic_factory")
def fx_sqlalchemy_pydantic_factory() -> MappedPydanticFactory:
    return sqlalchemy_pydantic_factory()


@pytest.fixture
def sync_query() -> type[DefaultQuery]:
    return DefaultQuery


@strawberry.type
class DefaultQuery:
    @strawberry.field
    def hello(self) -> str:
        return "World"
