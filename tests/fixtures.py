from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, override

import pytest
from strawchemy.mapper import Strawchemy
from syrupy.assertion import SnapshotAssertion
from syrupy.exceptions import TaintedSnapshotError
from syrupy.extensions.amber.serializer import AmberDataSerializer
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from tests.utils import sqlalchemy_dataclass_factory, sqlalchemy_pydantic_factory

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion
    from syrupy.data import SnapshotCollection
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

    from tests.typing import MappedDataclassFactory, MappedPydanticFactory

__all__ = ("sqlalchemy_dataclass_factory", "sqlalchemy_pydantic_factory", "strawchemy")


class GraphQLFileExtension(SingleFileSnapshotExtension):
    _write_mode = WriteMode.TEXT
    _file_extension = "gql"
    serializer_class: type[AmberDataSerializer] = AmberDataSerializer

    @override
    def serialize(
        self,
        data: SerializableData,
        *,
        exclude: PropertyFilter | None = None,
        include: PropertyFilter | None = None,
        matcher: PropertyMatcher | None = None,
    ) -> SerializedData:
        return self.serializer_class.serialize(data, exclude=exclude, include=include, matcher=matcher)

    @override
    def _read_snapshot_collection(self, *, snapshot_location: str) -> SnapshotCollection:
        return self.serializer_class.read_file(snapshot_location)

    @classmethod
    @lru_cache
    def __cacheable_read_snapshot(cls, snapshot_location: str, cache_key: str) -> SnapshotCollection:  # noqa: ARG003
        return cls.serializer_class.read_file(snapshot_location)

    @override
    def _read_snapshot_data_from_location(
        self, *, snapshot_location: str, snapshot_name: str, session_id: str
    ) -> SerializableData | None:
        snapshots = self.__cacheable_read_snapshot(snapshot_location=snapshot_location, cache_key=session_id)
        snapshot = snapshots.get(snapshot_name)
        tainted = bool(snapshots.tainted or (snapshot and snapshot.tainted))
        data = snapshot.data if snapshot else None
        if tainted:
            raise TaintedSnapshotError(snapshot_data=data)
        return data

    @override
    @classmethod
    def _write_snapshot_collection(cls, *, snapshot_collection: SnapshotCollection) -> None:
        cls.serializer_class.write_file(snapshot_collection, merge=True)


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.use_extension(GraphQLFileExtension)


@pytest.fixture
def strawchemy() -> Strawchemy[DeclarativeBase, QueryableAttribute[Any]]:
    return Strawchemy()


@pytest.fixture(name="sqlalchemy_dataclass_factory")
def fx_sqlalchemy_dataclass_factory() -> MappedDataclassFactory:
    return sqlalchemy_dataclass_factory()


@pytest.fixture(name="sqlalchemy_pydantic_factory")
def fx_sqlalchemy_pydantic_factory() -> MappedPydanticFactory:
    return sqlalchemy_pydantic_factory()
