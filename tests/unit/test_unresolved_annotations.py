from __future__ import annotations

from typing import Any

import pytest
import strawberry
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.exceptions import UnresolvedFieldTypeError
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from strawchemy.exceptions import StrawchemyFieldError


class _Base(DeclarativeBase): ...


class _Color(_Base):
    __tablename__ = "ua_color"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    fruits: Mapped[list[_Fruit]] = relationship("_Fruit", back_populates="color")


class _Fruit(_Base):
    __tablename__ = "ua_fruit"
    id: Mapped[int] = mapped_column(primary_key=True)
    color_id: Mapped[int] = mapped_column(ForeignKey("ua_color.id"))
    color: Mapped[_Color] = relationship("_Color", back_populates="fruits")


# Annotations resolve against module globals, so the forward-referenced class must be declared at
# module scope, after the inputs referencing it.
_sc = Strawchemy("sqlite")


@_sc.type(_Color, include=["id", "name"])
class _ColorType:
    extra: _Later | None = None


@_sc.filter(_Color, include=["id", "name"])
class _ColorFilter:
    extra: _Later | None = None


@_sc.order(_Color, include=["id", "name"])
class _ColorOrder:
    extra: _Later | None = None


@strawberry.input
class _Later:
    value: int


@pytest.mark.parametrize("dto", [_ColorType, _ColorFilter, _ColorOrder])
def test_late_declared_annotation_is_kept_as_forward_reference(dto: type[Any]) -> None:
    """Test that an annotation naming a class declared later reaches strawberry unevaluated."""
    extra = next(f for f in get_object_definition(dto, strict=True).fields if f.name == "extra")

    assert extra.type_annotation is not None
    assert extra.type_annotation.annotation == "_Later | None"


@pytest.mark.xfail(
    raises=UnresolvedFieldTypeError,
    strict=True,
    reason="generated DTOs resolve forward references against strawchemy's module, not the user's",
)
def test_late_declared_annotation_resolves_in_schema() -> None:
    """Test that the schema resolves an annotation naming a class declared after the inputs."""

    @strawberry.type
    class Query:
        colors: list[_ColorType] = _sc.field(filter_input=_ColorFilter, order_by=_ColorOrder)

    strawberry.Schema(query=Query)


@pytest.mark.parametrize("decorator", ["filter", "order"])
def test_unresolved_annotation_is_accepted(decorator: str) -> None:
    """Test that an unresolvable annotation on a non-declared field does not fail the decorator."""
    sc = Strawchemy("sqlite")

    class ColorInput:
        extra: _Undefined | None = None  # noqa: F821  # ty: ignore[unresolved-reference]

    getattr(sc, decorator)(_Color, include=["id", "name"])(ColorInput)


def test_unresolved_declared_filter_field_raises() -> None:
    """Test that a filter_field() whose annotation cannot be resolved raises, naming the attribute."""
    sc = Strawchemy("sqlite")

    with pytest.raises(StrawchemyFieldError, match=r"'name'.*'_Undefined'"):

        @sc.filter(_Color, include=["id"])
        class ColorFilter:
            name: _Undefined = sc.filter_field(ops=["eq"])  # noqa: F821  # ty: ignore[unresolved-reference]


def test_unresolved_declared_aggregate_raises() -> None:
    """Test that an unresolvable <relation>_aggregate annotation raises, naming the attribute."""
    sc = Strawchemy("sqlite")

    with pytest.raises(StrawchemyFieldError, match=r"'fruits_aggregate'.*'_Undefined'"):

        @sc.filter(_Color, include=["id", "fruits"])
        class ColorFilter:
            fruits_aggregate: _Undefined  # noqa: F821  # ty: ignore[unresolved-reference]
