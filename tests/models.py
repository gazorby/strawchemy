from __future__ import annotations

from uuid import UUID, uuid4

from strawchemy.dto.utils import PRIVATE, READ_ONLY, WRITE_ONLY

from sqlalchemy import VARCHAR, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def validate_fruit_type(value: str) -> None:
    if "rotten" in value:
        msg = "We do not allow rotten fruits."
        raise ValueError(msg)


class UUIDBase(DeclarativeBase):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    private: Mapped[str] = mapped_column(info=PRIVATE)


class NameDescriptionMixin(DeclarativeBase):
    __abstract__ = True

    name: Mapped[str] = mapped_column(VARCHAR)
    description: Mapped[str] = mapped_column(Text)


class Vegetable(UUIDBase, NameDescriptionMixin):
    __tablename__ = "vegetable"

    world_production: Mapped[float]


class Fruit(UUIDBase):
    __tablename__ = "fruit"

    name: Mapped[str]
    color_id: Mapped[UUID | None] = mapped_column(ForeignKey("color.id"))
    color: Mapped[Color] = relationship("Color", back_populates="fruits")
    sweetness: Mapped[int]

    def name_upper(self) -> str:
        return self.name.upper()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


class Tomato(UUIDBase):
    __tablename__ = "tomato"

    name: Mapped[str]


class Color(UUIDBase):
    __tablename__ = "color"

    fruits: Mapped[list[Fruit]] = relationship("Fruit", back_populates="color")
    name: Mapped[str]


class FruitType(UUIDBase):
    __tablename__ = "fruit_type"

    name: Mapped[str]


class User(UUIDBase):
    __tablename__ = "user"

    name: Mapped[str]
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("group.id"))
    group: Mapped[Group] = relationship("Group", back_populates="users")
    tag_id: Mapped[UUID | None] = mapped_column(ForeignKey("tag.id"))
    tag: Mapped[Tag] = relationship("Tag", uselist=False)

    @property
    def group_prop(self) -> Group | None:
        return self.group

    def get_group(self) -> Group | None:
        return self.group


class Group(UUIDBase):
    __tablename__ = "group"

    name: Mapped[str]
    users: Mapped[list[User]] = relationship("User", back_populates="group")


class Admin(UUIDBase):
    __tablename__ = "admin"

    name: Mapped[str]
    password: Mapped[str] = mapped_column(info=WRITE_ONLY)


class Tag(UUIDBase):
    __tablename__ = "tag"

    name: Mapped[str]


class Book(UUIDBase):
    __tablename__ = "book"

    title: Mapped[str]
    isbn: Mapped[str] = mapped_column(info=READ_ONLY)


try:
    from geoalchemy2 import Geometry, WKBElement

    geoalchemy_imported = True

    class GeoModel(UUIDBase):
        __tablename__ = "geos_fields"

        point_required: Mapped[WKBElement] = mapped_column(Geometry("POINT"))
        point: Mapped[WKBElement | None] = mapped_column(Geometry("POINT"), nullable=True)
        line_string: Mapped[WKBElement | None] = mapped_column(Geometry("LINESTRING"), nullable=True)
        polygon: Mapped[WKBElement | None] = mapped_column(Geometry("POLYGON"), nullable=True)
        multi_point: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOINT"), nullable=True)
        multi_line_string: Mapped[WKBElement | None] = mapped_column(Geometry("MULTILINESTRING"), nullable=True)
        multi_polygon: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON"), nullable=True)
        geometry: Mapped[WKBElement | None] = mapped_column(Geometry("GEOMETRY"), nullable=True)

except ModuleNotFoundError:
    geoalchemy_imported = False
