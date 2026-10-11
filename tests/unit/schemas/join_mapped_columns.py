"""A class mapped onto a ``join()`` through plain columns, so that its properties are writable, and its owner."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table, join
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class _Base(DeclarativeBase): ...


_a = Table(
    "column_join_a",
    _Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String),
    Column("owner_id", ForeignKey("column_join_owner.id")),
)
_b = Table(
    "column_join_b",
    _Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("a_id", ForeignKey("column_join_a.id")),
)


class ColumnJoinOwner(_Base):
    __tablename__ = "column_join_owner"

    id: Mapped[int] = mapped_column(primary_key=True)
    items: Mapped[list[ColumnJoinedAB]] = relationship()


class ColumnJoinedAB(_Base):
    __table__ = join(_a, _b)
    __mapper_args__ = {"properties": {"id": [_a.c.id, _b.c.a_id], "b_id": _b.c.id, "owner_id": _a.c.owner_id}}  # noqa: RUF012
    # Plain annotations give strawchemy the field types of the mapper properties above.
    __allow_unmapped__ = True

    id: int
    b_id: int
    name: str | None
    owner_id: int | None
