from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy import Column, DateTime, ForeignKey, MetaData, Table
from strawchemy.dto.utils import READ_ONLY

UTC = timezone.utc


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
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("project.id"), nullable=True, default=None)
    project: Mapped[Project | None] = relationship("Project", back_populates="milestones")


class Tag(Base):
    __tablename__ = "tag"

    name: Mapped[str]


class Project(Base):
    __tablename__ = "project"

    tag_id: Mapped[UUID | None] = mapped_column(ForeignKey("tag.id"), nullable=True, default=None)
    tickets: Mapped[list[Ticket]] = relationship(Ticket, back_populates="project")
    milestones: Mapped[list[Milestone]] = relationship(Milestone, back_populates="project")
    tag: Mapped[Tag | None] = relationship(Tag)
    name: Mapped[str]
    customers: Mapped[list[Customer]] = relationship(
        "Customer", back_populates="projects", secondary="customer_project_join"
    )


CustomerProjectJoin = Table(
    "customer_project_join",
    Base.metadata,
    Column("customer_id", ForeignKey("customer.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", ForeignKey("project.id", ondelete="CASCADE"), primary_key=True),
)


class Customer(Base):
    __tablename__ = "customer"

    projects: Mapped[list[Project]] = relationship(
        Project, back_populates="customers", secondary="customer_project_join"
    )
    name: Mapped[str]
