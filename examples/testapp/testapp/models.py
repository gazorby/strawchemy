from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from strawchemy.dto.utils import READ_ONLY

from sqlalchemy import DateTime, ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

metadata, geo_metadata = MetaData(), MetaData()


class Base(DeclarativeBase):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), info=READ_ONLY
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), info=READ_ONLY
    )


class Ticket(Base):
    __tablename__ = "ticket"

    name: Mapped[str]
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("project.id"), nullable=True, default=None)
    project: Mapped[Project | None] = relationship("Project", back_populates="tickets")


class Milestone(Base):
    __tablename__ = "milestone"
    name: Mapped[str]
    projects: Mapped[list[Project]] = relationship("Project", back_populates="milestone")


class Tag(Base):
    __tablename__ = "tag"

    name: Mapped[str]


class Project(Base):
    __tablename__ = "project"

    milestone_id: Mapped[UUID | None] = mapped_column(ForeignKey("milestone.id"), nullable=True, default=None)
    tag_id: Mapped[UUID | None] = mapped_column(ForeignKey("tag.id"), nullable=True, default=None)
    tickets: Mapped[list[Ticket]] = relationship(Ticket, back_populates="project")
    milestone: Mapped[Milestone | None] = relationship(Milestone, back_populates="projects")
    tag: Mapped[Tag | None] = relationship(Tag)
    name: Mapped[str]
