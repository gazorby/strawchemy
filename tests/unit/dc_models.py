from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import VARCHAR, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, column_property, mapped_column, relationship

from strawchemy.dto import Purpose, PurposeConfig, field
from strawchemy.dto.utils import WRITE_ONLY
from tests.unit.models import validate_tomato_type


class UUIDBase(MappedAsDataclass, DeclarativeBase):
    __abstract__ = True


class FruitDataclass(UUIDBase):
    __tablename__ = "fruit_dc"

    name: Mapped[str]
    color_id: Mapped[UUID | None] = mapped_column(ForeignKey("color_dataclass.id"))
    color: Mapped[ColorDataclass | None] = relationship("ColorDataclass", back_populates="fruits")
    sweetness: Mapped[int]
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)


class ColorDataclass(UUIDBase):
    __tablename__ = "color_dataclass"

    name: Mapped[str]
    fruits: Mapped[list[FruitDataclass]] = relationship("FruitDataclass", back_populates="color")
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)


class TomatoDataclass(UUIDBase):
    __tablename__ = "tomato"

    name: Mapped[str] = mapped_column(
        info=field(
            purposes={Purpose.READ, Purpose.WRITE},
            configs={Purpose.WRITE: PurposeConfig(validator=validate_tomato_type)},
        )
    )
    weight: Mapped[float] = mapped_column(info=field(configs={Purpose.WRITE: PurposeConfig(type_override=int)}))
    sweetness: Mapped[float] = mapped_column(info=field(configs={Purpose.WRITE: PurposeConfig(alias="sugarness")}))
    popularity: Mapped[float] = mapped_column(info=field(configs={Purpose.WRITE: PurposeConfig(partial=True)}))
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)


class AdminDataclass(UUIDBase):
    __tablename__ = "admin_dataclass"

    name: Mapped[str]
    password: Mapped[str] = mapped_column(info=WRITE_ONLY)
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)


class SponsoredUserDataclass(UUIDBase):
    __tablename__ = "sponsored_user_dataclass"

    name: Mapped[str]
    sponsor_id: Mapped[UUID | None] = mapped_column(ForeignKey("sponsored_user_dataclass.id"))
    sponsor: Mapped[SponsoredUserDataclass | None] = relationship("SponsoredUserDataclass", back_populates="sponsored")
    sponsored: Mapped[list[SponsoredUserDataclass]] = relationship(
        "SponsoredUserDataclass",
        back_populates="sponsor",
        remote_side="SponsoredUserDataclass.id",
        default_factory=list,
        uselist=True,
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)


class UserWithGreetingDataclass(UUIDBase):
    __tablename__ = "user_with_greeting_dataclass"

    name: Mapped[str] = mapped_column()
    greeting_column_property: Mapped[str] = column_property("Hello, " + name)
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)

    @hybrid_property
    def greeting_hybrid_property(self) -> str:
        return f"Hello, {self.name}"


class NullableTestModelDataclass(UUIDBase):
    __tablename__ = "nullable_test_dataclass"

    # Style 3: Type hint NOT optional, no explicit nullable (infers nullable=False, both agree)
    non_optional_nullable_not_set: Mapped[str] = mapped_column(VARCHAR(255))

    # Style 6: Type hint NOT optional + explicit nullable=False (both agree)
    non_optional_nullable_false: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)

    # Style 1: Type hint optional + explicit nullable=True (both agree)
    optional_nullable_true: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True, default=None)

    # Style 2: Type hint NOT optional + explicit nullable=True (MISMATCH)
    non_optional_nullable_true: Mapped[str] = mapped_column(VARCHAR(255), nullable=True, default="")

    # Style 4: Type hint optional, no explicit nullable (infers nullable=True)
    optional_nullable_not_set: Mapped[str | None] = mapped_column(VARCHAR(255), default=None)

    # Style 5: Type hint optional + explicit nullable=False (MISMATCH opposite)
    optional_nullable_false: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=False, default="")

    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)
