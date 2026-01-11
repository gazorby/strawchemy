from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from syrupy.exceptions import TaintedSnapshotError
from syrupy.extensions.amber.serializer import AmberDataSerializer
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode
from typing_extensions import override

if TYPE_CHECKING:
    from syrupy.data import SnapshotCollection
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

__all__ = ("GraphQLFileExtension", "SQLFileExtension", "SingleAmberFileExtension")


class SingleAmberFileExtension(SingleFileSnapshotExtension):
    _write_mode = WriteMode.TEXT
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

    def _read_snapshot_collection(self, *, snapshot_location: str) -> SnapshotCollection:
        return self.serializer_class.read_file(snapshot_location)

    @classmethod
    @lru_cache
    def __cacheable_read_snapshot(cls, snapshot_location: str, cache_key: str) -> SnapshotCollection:  # noqa: ARG003
        return cls.serializer_class.read_file(snapshot_location)

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

    @classmethod
    def _write_snapshot_collection(cls, *, snapshot_collection: SnapshotCollection) -> None:
        cls.serializer_class.write_file(snapshot_collection, merge=True)


class GraphQLFileExtension(SingleAmberFileExtension):
    file_extension = "gql"


class SQLFileExtension(SingleAmberFileExtension):
    file_extension = "sql"
