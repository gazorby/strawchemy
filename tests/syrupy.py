from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from syrupy.exceptions import TaintedSnapshotError
from syrupy.extensions.amber import AmberSnapshotExtension
from syrupy.extensions.amber.serializer import AmberDataSerializer
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode
from syrupy.utils import exclusive_file_lock
from typing_extensions import override

if TYPE_CHECKING:
    from syrupy.data import SnapshotCollection
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

__all__ = (
    "GraphQLFileExtension",
    "SQLFileExtension",
    "SingleAmberFileExtension",
    "SnapshotMergeError",
    "VerifiedAmberSnapshotExtension",
)


class SnapshotMergeError(RuntimeError):
    """A merged amber write dropped entries that were on disk."""


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


class VerifiedAmberSnapshotExtension(AmberSnapshotExtension):
    @classmethod
    @override
    def write_snapshot_collection(
        cls, *, snapshot_collection: SnapshotCollection, name_order: dict[str, int] | None = None
    ) -> None:
        location = snapshot_collection.location
        # Reading the entries before and after the merge only proves anything while no other
        # process can write in between, so the whole check runs inside the write lock.
        with exclusive_file_lock(location):
            expected = _entry_names(cls.serializer_class.read_file(location)) | _entry_names(snapshot_collection)
            cls.serializer_class.write_file(
                snapshot_collection, merge=True, name_order=name_order, file_lock=True, _already_locked=True
            )
            dropped = expected - _entry_names(cls.serializer_class.read_file(location))
        if dropped:
            msg = (
                f"Merged write of '{location}' dropped {len(dropped)} entries, "
                f"starting with '{min(dropped)}'. Concurrent writers clobbered the file: "
                f"restore it, then re-run the update with --snapshot-file-lock or -n=0."
            )
            raise SnapshotMergeError(msg)


def _entry_names(snapshot_collection: SnapshotCollection) -> set[str]:
    return {snapshot.name for snapshot in snapshot_collection}
