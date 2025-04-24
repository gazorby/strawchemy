# ruff: noqa: TC003

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from strawchemy.dto.utils import PRIVATE, READ_ONLY

from sqlalchemy import DateTime, ForeignKey, MetaData, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column, relationship
from sqlalchemy.orm import registry as Registry  # noqa: N812

metadata, geo_metadata = MetaData(), MetaData()


class BaseColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), info=READ_ONLY
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), info=READ_ONLY
    )


class UUIDBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=metadata)


class GeoUUIDBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=geo_metadata)


class FruitFarm(UUIDBase):
    __tablename__ = "fruit_farm"

    name: Mapped[str]
    fruit_id: Mapped[UUID] = mapped_column(ForeignKey("fruit.id"), info=PRIVATE)


class DerivedProduct(UUIDBase):
    __tablename__ = "derived_product"

    name: Mapped[str]


class Fruit(UUIDBase):
    __tablename__ = "fruit"

    name: Mapped[str]
    color_id: Mapped[UUID | None] = mapped_column(ForeignKey("color.id"), nullable=True, default=None)
    adjectives: Mapped[list[str]] = mapped_column(postgresql.ARRAY(Text), default=list)
    color: Mapped[Color | None] = relationship("Color", back_populates="fruits")
    farms: Mapped[list[FruitFarm]] = relationship(FruitFarm)
    derived_product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("derived_product.id"), nullable=True, default=None
    )
    product: Mapped[DerivedProduct | None] = relationship(DerivedProduct)

    @hybrid_property
    def description(self) -> str:
        return f"The {self.name} is {', '.join(self.adjectives)}"


class Color(UUIDBase):
    __tablename__ = "color"

    fruits: Mapped[list[Fruit]] = relationship("Fruit", back_populates="color")
    name: Mapped[str]


class Group(UUIDBase):
    __tablename__ = "group"

    name: Mapped[str] = mapped_column()
    topics: Mapped[list["Topic"]] = relationship("Topic")


class Topic(UUIDBase):
    __tablename__ = "topic"

    name: Mapped[str] = mapped_column()
    group_id: Mapped[UUID] = mapped_column(ForeignKey("group.id"))


class User(UUIDBase):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column()
    greeting: Mapped[str] = column_property("Hello, " + name)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("group.id"))
    group: Mapped[Group | None] = relationship(Group)


class RankedUser(UUIDBase):
    __tablename__ = "ranked_user"

    name: Mapped[str] = mapped_column()
    rank: Mapped[int] = mapped_column(info=READ_ONLY)


class SQLDataTypes(UUIDBase):
    __tablename__ = "sql_data_types"

    date_col: Mapped[date]
    time_col: Mapped[time]
    time_delta_col: Mapped[timedelta]
    datetime_col: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    str_col: Mapped[str]
    int_col: Mapped[int]
    float_col: Mapped[float]
    decimal_col: Mapped[Decimal]
    bool_col: Mapped[bool]
    uuid_col: Mapped[UUID]
    dict_col: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, default=dict)
    array_str_col: Mapped[list[str]] = mapped_column(postgresql.ARRAY(Text), default=list)
    optional_str_col: Mapped[str | None] = mapped_column(nullable=True, default=None)
    container_id: Mapped[UUID] = mapped_column(ForeignKey("sql_data_types_container.id"))
    container: Mapped[SQLDataTypesContainer] = relationship("SQLDataTypesContainer")


class SQLDataTypesContainer(UUIDBase):
    __tablename__ = "sql_data_types_container"

    data_types: Mapped[list[SQLDataTypes]] = relationship("SQLDataTypes", back_populates="container")
