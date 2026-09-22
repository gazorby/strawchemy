from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


post_tag = Table(
    "post_tag",
    Base.metadata,
    Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]
    posts: Mapped[list[Post]] = relationship("Post", back_populates="author")


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    views: Mapped[int] = mapped_column(default=0)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), default=None)
    author: Mapped[User | None] = relationship("User", back_populates="posts")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary=post_tag, back_populates="posts")


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list[Post]] = relationship("Post", secondary=post_tag, back_populates="tags")
