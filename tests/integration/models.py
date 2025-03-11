# ruff: noqa: TC003

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DECIMAL, JSON, Date, DateTime, ForeignKey, MetaData, Text, Time
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, registry, relationship

metadata = MetaData()
registry = registry(metadata=metadata)


class BaseColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class UUIDBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = registry


class Fruit(UUIDBase):
    __tablename__ = "fruit"

    name: Mapped[str]
    color_id: Mapped[UUID | None] = mapped_column(ForeignKey("color.id"), nullable=True, default=None)
    sweetness: Mapped[int]
    has_core: Mapped[bool]
    adjectives: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    price_decimal: Mapped[Decimal] = mapped_column(DECIMAL(asdecimal=True))
    price_float: Mapped[float]
    color: Mapped[Color | None] = relationship("Color", back_populates="fruits")

    @hybrid_property
    def description(self) -> str:
        return f"The {self.name} is {', '.join(self.adjectives)}"


class Color(UUIDBase):
    __tablename__ = "color"

    fruits: Mapped[list[Fruit]] = relationship("Fruit", back_populates="color")
    name: Mapped[str]


class User(UUIDBase):
    __tablename__ = "user"

    name: Mapped[str]
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    birthday: Mapped[date] = mapped_column(Date)
    newsletter_send_time: Mapped[time] = mapped_column(Time, default=lambda: time(hour=8))
