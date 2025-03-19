# ruff: noqa: TC003

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from geoalchemy2 import Geometry, WKBElement

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm import registry as Registry  # noqa: N812

metadata, geo_metadata = MetaData(), MetaData()


class BaseColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class GeoUUIDBase(BaseColumns, DeclarativeBase):
    __abstract__ = True
    registry = Registry(metadata=geo_metadata)


class GeoModel(GeoUUIDBase):
    __tablename__ = "geos_fields"

    point_required: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))
    point: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    line_string: Mapped[WKBElement | None] = mapped_column(Geometry("LINESTRING", srid=4326), nullable=True)
    polygon: Mapped[WKBElement | None] = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    multi_point: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOINT", srid=4326), nullable=True)
    multi_line_string: Mapped[WKBElement | None] = mapped_column(Geometry("MULTILINESTRING", srid=4326), nullable=True)
    multi_polygon: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    geometry: Mapped[WKBElement | None] = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
