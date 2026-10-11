"""DB-free strawchemy schema over a class mapped onto a ``join()``, reached as a relation of ``JoinOwner``.

``JoinedAB`` maps ``a.id`` and ``b.id``, two primary key columns sharing the key ``id``, to ``id`` and ``b_id``, and
``a.owner_id`` to ``owner_ref``.
"""

from __future__ import annotations

import strawberry
from sqlalchemy import Column, ForeignKey, Integer, String, Table, join
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column, relationship

from strawchemy import Strawchemy


class _Base(DeclarativeBase): ...


_a = Table(
    "join_a",
    _Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String),
    Column("owner_id", ForeignKey("join_owner.id")),
)
_b = Table("join_b", _Base.metadata, Column("id", Integer, primary_key=True), Column("a_id", ForeignKey("join_a.id")))


class JoinOwner(_Base):
    __tablename__ = "join_owner"

    id: Mapped[int] = mapped_column(primary_key=True)
    abs: Mapped[list[JoinedAB]] = relationship(viewonly=True)


class JoinedAB(_Base):
    __table__ = join(_a, _b)

    id: Mapped[int] = column_property(_a.c.id, _b.c.a_id)
    b_id: Mapped[int] = column_property(_b.c.id)
    name: Mapped[str | None] = column_property(_a.c.name)
    owner_ref: Mapped[int | None] = column_property(_a.c.owner_id)
    children: Mapped[list[JoinChild]] = relationship(viewonly=True)


class JoinChild(_Base):
    __tablename__ = "join_child"

    id: Mapped[int] = mapped_column(primary_key=True)
    b_id: Mapped[int] = mapped_column(ForeignKey("join_b.id"))


strawchemy = Strawchemy("postgresql")


@strawchemy.type(JoinChild, include="all")
class JoinChildType: ...


@strawchemy.type(JoinedAB, include="all", paginate="all")
class JoinedABType: ...


@strawchemy.type(JoinOwner, include="all", paginate="all")
class JoinOwnerType: ...


@strawberry.type
class Query:
    owners: list[JoinOwnerType] = strawchemy.field()


schema = strawberry.Schema(query=Query)
