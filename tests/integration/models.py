# ruff: noqa: TC003

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from strawchemy.dto.utils import PRIVATE, READ_ONLY

from sqlalchemy import ARRAY, JSON, DateTime, ForeignKey, MetaData, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, column_property, mapped_column, relationship
from sqlalchemy.orm import registry as Registry  # noqa: N812

metadata = MetaData()
geo_metadata = MetaData()
dc_metadata = MetaData()
json_metadata = MetaData()
array_metadata = MetaData()
interval_metadata = MetaData()
date_time_metadata = MetaData()


TextArrayType = ARRAY(Text).with_variant(postgresql.ARRAY(Text), "postgresql")
JSONType = JSON().with_variant(postgresql.JSONB, "postgresql")


# Bases


class BaseColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), info=READ_ONLY
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), info=READ_ONLY
    )


class Base(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=metadata)


class DataclassBase(BaseColumns, MappedAsDataclass, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=dc_metadata)


class GeoUUIDBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=geo_metadata)


class ArrayBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=array_metadata)


class JSONBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=json_metadata)


class IntervalBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=interval_metadata)


class DateTimeBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=date_time_metadata)


# Models


class FruitFarm(Base):
    __tablename__ = "fruit_farm"

    name: Mapped[str]
    fruit_id: Mapped[UUID] = mapped_column(ForeignKey("fruit.id"), info=PRIVATE)


class DerivedProduct(Base):
    __tablename__ = "derived_product"

    name: Mapped[str]


class Fruit(Base):
    __tablename__ = "fruit"

    name: Mapped[str]
    color_id: Mapped[UUID | None] = mapped_column(ForeignKey("color.id"), nullable=True, default=None)
    color: Mapped[Color | None] = relationship("Color", back_populates="fruits")
    farms: Mapped[list[FruitFarm]] = relationship(FruitFarm)
    derived_product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("derived_product.id"), nullable=True, default=None
    )
    product: Mapped[DerivedProduct | None] = relationship(DerivedProduct)
    sweetness: Mapped[int]
    water_percent: Mapped[float]
    rarity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    best_time_to_pick: Mapped[time] = mapped_column(default=time(hour=9))

    @hybrid_property
    def description(self) -> str:
        return f"The {self.name} color id is {self.color_id}"


class Color(Base):
    __tablename__ = "color"

    fruits: Mapped[list[Fruit]] = relationship("Fruit", back_populates="color")
    name: Mapped[str]


class Group(Base):
    __tablename__ = "group"

    name: Mapped[str] = mapped_column()
    topics: Mapped[list["Topic"]] = relationship("Topic")


class Topic(Base):
    __tablename__ = "topic"

    name: Mapped[str] = mapped_column()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("group.id"))


class User(Base):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column()
    greeting: Mapped[str] = column_property("Hello, " + name)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("group.id"))
    group: Mapped[Group | None] = relationship(Group)
    bio: Mapped[str | None] = mapped_column(default=None)

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        if self.bio is None:
            self.bio = "Lorem ipsum dolor sit amet, consectetur adipiscing elit"


class RankedUser(Base):
    __tablename__ = "ranked_user"

    name: Mapped[str] = mapped_column()
    rank: Mapped[int] = mapped_column(info=READ_ONLY)


# Specific data types models


class ArrayModel(ArrayBase):
    __tablename__ = "array_model"

    array_str_col: Mapped[list[str]] = mapped_column(TextArrayType, default=list)


class IntervalModel(IntervalBase):
    __tablename__ = "interval_model"

    registry = Registry(metadata=interval_metadata)

    time_delta_col: Mapped[timedelta]


class JSONModel(JSONBase):
    __tablename__ = "json_model"

    registry = Registry(metadata=json_metadata)

    dict_col: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class DateTimeModel(DateTimeBase):
    __tablename__ = "date_time_model"

    registry = Registry(metadata=date_time_metadata)

    date_col: Mapped[date]
    time_col: Mapped[time]
    datetime_col: Mapped[datetime] = mapped_column(DateTime(timezone=True))
