"""Queries and mutations on models mapped onto a ``Table`` through ``__table__`` instead of ``__tablename__``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Column, ForeignKey, Insert, Integer, MetaData, String, Table, insert
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship

from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.utils import maybe_async

if TYPE_CHECKING:
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_metadata = MetaData()

_author_table = Table(
    "table_mapped_author", _metadata, Column("id", Integer, primary_key=True), Column("name", String(50))
)
_book_table = Table(
    "table_mapped_book",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(50)),
    Column("author_id", ForeignKey("table_mapped_author.id")),
)


class _Base(DeclarativeBase):
    metadata = _metadata


class _Author(_Base):
    __table__ = _author_table

    books: Mapped[list[_Book]] = relationship("_Book", back_populates="author")


class _Book(_Base):
    __table__ = _book_table

    author: Mapped[_Author] = relationship(_Author, back_populates="books")


_strawchemy = Strawchemy("postgresql")


@_strawchemy.type(_Author, include="all")
class AuthorType: ...


@_strawchemy.type(_Book, include="all")
class BookType: ...


@_strawchemy.create_input(_Book, include="all")
class BookCreateInput: ...


@_strawchemy.pk_update_input(_Book, include="all")
class BookUpdateInput: ...


@_strawchemy.filter(_Book, include="all")
class BookFilter: ...


@strawberry.type
class AsyncQuery:
    books: list[BookType] = _strawchemy.field(repository_type=StrawchemyAsyncRepository)
    books_paginated: list[BookType] = _strawchemy.field(pagination=True, repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    books: list[BookType] = _strawchemy.field(repository_type=StrawchemySyncRepository)
    books_paginated: list[BookType] = _strawchemy.field(pagination=True, repository_type=StrawchemySyncRepository)


@strawberry.type
class AsyncMutation:
    create_book: BookType = _strawchemy.create(BookCreateInput, repository_type=StrawchemyAsyncRepository)
    update_book: BookType = _strawchemy.update_by_ids(BookUpdateInput, repository_type=StrawchemyAsyncRepository)
    delete_books: list[BookType] = _strawchemy.delete(BookFilter, repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncMutation:
    create_book: BookType = _strawchemy.create(BookCreateInput, repository_type=StrawchemySyncRepository)
    update_book: BookType = _strawchemy.update_by_ids(BookUpdateInput, repository_type=StrawchemySyncRepository)
    delete_books: list[BookType] = _strawchemy.delete(BookFilter, repository_type=StrawchemySyncRepository)


@pytest.fixture
def metadata() -> MetaData:
    return _metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(_Author).values([{"id": 1, "name": "Ursula"}]),
        insert(_Book).values(
            [{"id": 1, "title": "Earthsea", "author_id": 1}, {"id": 2, "title": "The Dispossessed", "author_id": 1}]
        ),
    ]


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_mutation() -> type[AsyncMutation]:
    return AsyncMutation


@pytest.fixture
def sync_mutation() -> type[SyncMutation]:
    return SyncMutation


async def test_query(any_query: AnyQueryExecutor) -> None:
    """Test that a ``__table__``-mapped model and its relation are queried."""
    result = await maybe_async(any_query("{ books { title author { name books { id } } } }"))

    assert not result.errors
    assert result.data
    author = {"name": "Ursula", "books": [{"id": 1}, {"id": 2}]}
    assert result.data["books"] == [
        {"title": "Earthsea", "author": author},
        {"title": "The Dispossessed", "author": author},
    ]


async def test_paginated_query(any_query: AnyQueryExecutor) -> None:
    """Test that a paginated root over a ``__table__``-mapped model reads its page from a subquery."""
    result = await maybe_async(any_query("{ booksPaginated(limit: 1, offset: 1) { title } }"))

    assert not result.errors
    assert result.data
    assert result.data["booksPaginated"] == [{"title": "The Dispossessed"}]


async def test_create(any_query: AnyQueryExecutor) -> None:
    """Test that creating a ``__table__``-mapped model returns the created row."""
    result = await maybe_async(
        any_query(
            """
            mutation {
                createBook(data: { id: 3, title: "Lavinia", author: { set: { id: 1 } } }) { title author { name } }
            }
            """
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["createBook"] == {"title": "Lavinia", "author": {"name": "Ursula"}}


async def test_update(any_query: AnyQueryExecutor) -> None:
    """Test that updating a ``__table__``-mapped model by id returns the updated row."""
    result = await maybe_async(any_query('mutation { updateBook(data: { id: 1, title: "Tehanu" }) { id title } }'))

    assert not result.errors
    assert result.data
    assert result.data["updateBook"] == {"id": 1, "title": "Tehanu"}


async def test_delete(any_query: AnyQueryExecutor) -> None:
    """Test that deleting ``__table__``-mapped models by filter returns the deleted rows."""
    result = await maybe_async(any_query("mutation { deleteBooks(filter: { id: { eq: 2 } }) { id title } }"))

    assert not result.errors
    assert result.data
    assert result.data["deleteBooks"] == [{"id": 2, "title": "The Dispossessed"}]
