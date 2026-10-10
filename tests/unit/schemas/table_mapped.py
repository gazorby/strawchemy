"""DB-free strawchemy schema over models mapped with ``__table__`` instead of ``__tablename__``."""

from __future__ import annotations

import strawberry
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship

from strawchemy import Strawchemy


class _Base(DeclarativeBase): ...


author_table = Table(
    "table_mapped_author", _Base.metadata, Column("id", Integer, primary_key=True), Column("name", String)
)
book_table = Table(
    "table_mapped_book",
    _Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String),
    Column("author_id", ForeignKey("table_mapped_author.id")),
)


class Author(_Base):
    __table__ = author_table

    books: Mapped[list[Book]] = relationship("Book", back_populates="author")


class Book(_Base):
    __table__ = book_table

    author: Mapped[Author] = relationship(Author, back_populates="books")


strawchemy = Strawchemy("postgresql")


@strawchemy.type(Author, include="all", override=True)
class AuthorType: ...


@strawchemy.type(Book, include="all", override=True)
class BookType: ...


@strawberry.type
class Query:
    books: list[BookType] = strawchemy.field()
    books_paginated: list[BookType] = strawchemy.field(pagination=True)


schema = strawberry.Schema(query=Query)
