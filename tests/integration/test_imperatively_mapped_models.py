"""Queries and mutations on models mapped through ``registry.map_imperatively``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Column, ForeignKey, Insert, Integer, MetaData, String, Table, insert
from sqlalchemy.orm import registry, relationship

from strawchemy import Strawchemy, StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.utils import maybe_async

if TYPE_CHECKING:
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_metadata = MetaData()

_author_table = Table(
    "imperative_author", _metadata, Column("id", Integer, primary_key=True), Column("name", String(50))
)
_book_table = Table(
    "imperative_book",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(50)),
    Column("author_id", ForeignKey("imperative_author.id")),
)
_vehicle_table = Table(
    "imperative_vehicle",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    Column("kind", String(10)),
)


class _Author:
    pass


class _Book:
    pass


class _Vehicle:
    pass


class _Car(_Vehicle):
    pass


_registry = registry(metadata=_metadata)
_registry.map_imperatively(_Author, _author_table, properties={"books": relationship(_Book, back_populates="author")})
_registry.map_imperatively(_Book, _book_table, properties={"author": relationship(_Author, back_populates="books")})
_registry.map_imperatively(
    _Vehicle, _vehicle_table, polymorphic_on=_vehicle_table.c.kind, polymorphic_identity="vehicle"
)
_registry.map_imperatively(_Car, None, inherits=_Vehicle, polymorphic_identity="car")


_strawchemy = Strawchemy("postgresql")


@_strawchemy.type(_Author, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class AuthorType: ...


@_strawchemy.type(_Book, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class BookType: ...


@_strawchemy.create_input(_Book, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class BookCreateInput: ...


@_strawchemy.pk_update_input(_Book, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class BookUpdateInput: ...


@_strawchemy.filter(_Book, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class BookFilter: ...


@_strawchemy.type(_Car, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class CarType: ...


@_strawchemy.pk_update_input(_Car, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class CarUpdateInput: ...


@_strawchemy.filter(_Car, include="all")  # ty: ignore[invalid-argument-type]  # imperatively mapped, not a DeclarativeBase
class CarFilter: ...


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
    update_car: CarType = _strawchemy.update_by_ids(CarUpdateInput, repository_type=StrawchemyAsyncRepository)
    delete_cars: list[CarType] = _strawchemy.delete(CarFilter, repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncMutation:
    create_book: BookType = _strawchemy.create(BookCreateInput, repository_type=StrawchemySyncRepository)
    update_book: BookType = _strawchemy.update_by_ids(BookUpdateInput, repository_type=StrawchemySyncRepository)
    delete_books: list[BookType] = _strawchemy.delete(BookFilter, repository_type=StrawchemySyncRepository)
    update_car: CarType = _strawchemy.update_by_ids(CarUpdateInput, repository_type=StrawchemySyncRepository)
    delete_cars: list[CarType] = _strawchemy.delete(CarFilter, repository_type=StrawchemySyncRepository)


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
        insert(_Vehicle).values(
            [{"id": 1, "name": "Cart", "kind": "vehicle"}, {"id": 2, "name": "Coupe", "kind": "car"}]
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
    """Test that an imperatively mapped model and its relation are queried."""
    result = await maybe_async(any_query("{ books { title author { name books { id } } } }"))

    assert not result.errors
    assert result.data
    author = {"name": "Ursula", "books": [{"id": 1}, {"id": 2}]}
    assert result.data["books"] == [
        {"title": "Earthsea", "author": author},
        {"title": "The Dispossessed", "author": author},
    ]


async def test_paginated_query(any_query: AnyQueryExecutor) -> None:
    """Test that a paginated root over an imperatively mapped model reads its page from a subquery."""
    result = await maybe_async(any_query("{ booksPaginated(limit: 1, offset: 1) { title } }"))

    assert not result.errors
    assert result.data
    assert result.data["booksPaginated"] == [{"title": "The Dispossessed"}]


async def test_create(any_query: AnyQueryExecutor) -> None:
    """Test that creating an imperatively mapped model returns the created row."""
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
    """Test that updating an imperatively mapped model by id returns the updated row."""
    result = await maybe_async(any_query('mutation { updateBook(data: { id: 1, title: "Tehanu" }) { id title } }'))

    assert not result.errors
    assert result.data
    assert result.data["updateBook"] == {"id": 1, "title": "Tehanu"}


async def test_delete(any_query: AnyQueryExecutor) -> None:
    """Test that deleting imperatively mapped models by filter returns the deleted rows."""
    result = await maybe_async(any_query("mutation { deleteBooks(filter: { id: { eq: 2 } }) { id title } }"))

    assert not result.errors
    assert result.data
    assert result.data["deleteBooks"] == [{"id": 2, "title": "The Dispossessed"}]


async def test_update_single_table_subclass(any_query: AnyQueryExecutor) -> None:
    """Test that updating an imperatively mapped single-table subclass by id returns the updated row."""
    result = await maybe_async(any_query('mutation { updateCar(data: { id: 2, name: "Sedan" }) { id name } }'))

    assert not result.errors
    assert result.data
    assert result.data["updateCar"] == {"id": 2, "name": "Sedan"}


async def test_delete_single_table_subclass(any_query: AnyQueryExecutor) -> None:
    """Test that deleting an imperatively mapped single-table subclass by filter deletes only its own rows."""
    result = await maybe_async(any_query("mutation { deleteCars(filter: { id: { gt: 0 } }) { id name } }"))

    assert not result.errors
    assert result.data
    assert result.data["deleteCars"] == [{"id": 2, "name": "Coupe"}]
