"""Relations to a class mapped onto a ``join()``, whose ``id`` property maps a column of each joined table."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Column, ForeignKey, Insert, Integer, MetaData, String, Table, insert, join
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column, relationship

from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]


class _Base(DeclarativeBase):
    metadata = MetaData()


_a = Table(
    "join_mapped_a",
    _Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("name", String(32)),
    Column("owner_id", ForeignKey("join_mapped_owner.id")),
)
_b = Table(
    "join_mapped_b",
    _Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("a_id", ForeignKey("join_mapped_a.id")),
)


class _Owner(_Base):
    __tablename__ = "join_mapped_owner"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    items: Mapped[list[_Item]] = relationship(viewonly=True)


class _Item(_Base):
    __table__ = join(_a, _b)

    id: Mapped[int] = column_property(_a.c.id, _b.c.a_id)
    b_id: Mapped[int] = column_property(_b.c.id)
    name: Mapped[str | None] = column_property(_a.c.name)
    owner_id: Mapped[int | None] = column_property(_a.c.owner_id)


_ITEMS = [
    {"id": 1, "b_id": 10, "name": "x", "owner_id": 1},
    {"id": 2, "b_id": 20, "name": "y", "owner_id": 1},
    {"id": 3, "b_id": 30, "name": "z", "owner_id": 2},
]


@cache
def _queries(dialect: SupportedDialect) -> tuple[type[Any], type[Any]]:
    """Builds the sync and async queries of ``dialect``, which sets whether relations join LATERAL or a CTE."""
    strawchemy = Strawchemy(dialect)

    @strawchemy.type(_Item, include="all")
    class ItemType: ...

    @strawchemy.type(_Owner, include="all", paginate="all")
    class OwnerType: ...

    @strawberry.type
    class SyncQuery:
        owners: list[OwnerType] = strawchemy.field(repository_type=StrawchemySyncRepository)

    @strawberry.type
    class AsyncQuery:
        owners: list[OwnerType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)

    return SyncQuery, AsyncQuery


@pytest.fixture
def metadata() -> MetaData:
    """Creates only this module's tables."""
    return _Base.metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    """Seeds two owners, the first with two items."""
    return [
        insert(_Owner).values([{"id": 1}, {"id": 2}]),
        insert(_a).values([{"id": item["id"], "name": item["name"], "owner_id": item["owner_id"]} for item in _ITEMS]),
        insert(_b).values([{"id": item["b_id"], "a_id": item["id"]} for item in _ITEMS]),
    ]


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    """Returns the sync query of ``dialect``."""
    return _queries(dialect)[0]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    """Returns the async query of ``dialect``."""
    return _queries(dialect)[1]


@pytest.fixture
def sync_mutation() -> None:
    """Leaves the schema without mutations."""


@pytest.fixture
def async_mutation() -> None:
    """Leaves the schema without mutations."""


def _items_of(owner_id: int) -> list[dict[str, Any]]:
    return [
        {"id": item["id"], "bId": item["b_id"], "name": item["name"]} for item in _ITEMS if item["owner_id"] == owner_id
    ]


async def test_paginated_relation_to_join_mapped_class(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a paged relation to a join-mapped class returns each related row once, joining no bare table."""
    result = await maybe_async(any_query("{ owners { id items { id bId name } } }"))

    assert not result.errors
    assert result.data == {"owners": [{"id": 1, "items": _items_of(1)}, {"id": 2, "items": _items_of(2)}]}
    assert query_tracker.query_count == 1


async def test_shared_relation_to_join_mapped_class(any_query: AnyQueryExecutor, query_tracker: QueryTracker) -> None:
    """Test that two pages of a relation to a join-mapped class, read once, each return their rows."""
    result = await maybe_async(
        any_query("{ owners { id first: items(limit: 1) { id bId name } rest: items(offset: 1) { id bId name } } }")
    )

    assert not result.errors
    assert result.data == {
        "owners": [
            {"id": 1, "first": _items_of(1)[:1], "rest": _items_of(1)[1:]},
            {"id": 2, "first": _items_of(2)[:1], "rest": []},
        ]
    }
    assert query_tracker.query_count == 1
