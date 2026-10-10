from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import strawberry
from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import get_object_definition
from strawberry.types.base import StrawberryObjectDefinition

from strawchemy import Strawchemy
from strawchemy.dto.types import FieldSpec
from strawchemy.schema.mutation import Input
from tests.unit.dc_models import ColorDataclass, FruitDataclass
from tests.unit.models import Color, Fruit

_MUTATION_INPUT_DECORATORS = ["create_input", "pk_update_input", "filter_update_input"]


class _CompositeKeyBase(DeclarativeBase):
    pass


class _Basket(_CompositeKeyBase):
    __tablename__ = "basket"

    id: Mapped[int] = mapped_column(primary_key=True)


class _BasketItem(_CompositeKeyBase):
    __tablename__ = "basket_item"

    basket_id: Mapped[int] = mapped_column(ForeignKey("basket.id"), primary_key=True)
    label: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str | None]
    basket: Mapped[_Basket] = relationship(_Basket)


class _ForeignKeyBase(DeclarativeBase):
    pass


_tag_fruit = Table(
    "tag_fruit",
    _ForeignKeyBase.metadata,
    Column("tag_id", ForeignKey("tag.id"), primary_key=True),
    Column("fruit_id", ForeignKey("fruit.id"), primary_key=True),
)


class _Fruit(_ForeignKeyBase):
    __tablename__ = "fruit"

    id: Mapped[int] = mapped_column(primary_key=True)
    labels: Mapped[list[_FruitLabel]] = relationship("_FruitLabel")
    stickers: Mapped[list[_Sticker]] = relationship("_Sticker", back_populates="fruit")


class _FruitLabel(_ForeignKeyBase):
    __tablename__ = "fruit_label"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruit_id: Mapped[int] = mapped_column(ForeignKey("fruit.id"))
    name: Mapped[str]


class _Sticker(_ForeignKeyBase):
    __tablename__ = "sticker"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruit_id: Mapped[int] = mapped_column(ForeignKey("fruit.id"))
    fruit: Mapped[_Fruit] = relationship(_Fruit, back_populates="stickers")


class _Badge(_ForeignKeyBase):
    __tablename__ = "badge"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruit_id: Mapped[int] = mapped_column(ForeignKey("fruit.id"))
    fruit: Mapped[_Fruit] = relationship(_Fruit, viewonly=True)


class _Tag(_ForeignKeyBase):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    fruit_id: Mapped[int] = mapped_column(ForeignKey("fruit.id"))
    fruits: Mapped[list[_Fruit]] = relationship(_Fruit, secondary=_tag_fruit)


def _input_field_names(decorator: str, model: type[DeclarativeBase], **kwargs: Any) -> set[str]:
    strawchemy = Strawchemy("postgresql")

    @getattr(strawchemy, decorator)(model, **kwargs)
    class ModelInput: ...

    return {field.name for field in get_object_definition(ModelInput, strict=True).fields}


@pytest.mark.parametrize("decorator", _MUTATION_INPUT_DECORATORS)
@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        pytest.param(_FruitLabel, {"include": "all"}, id="no-relationship"),
        pytest.param(_Tag, {"include": "all"}, id="many-to-many-only"),
        pytest.param(_Sticker, {"include": "all", "exclude": ["fruit"]}, id="relationship-excluded"),
        pytest.param(_Sticker, {"include": ["id", "fruit_id"]}, id="relationship-not-included"),
    ],
)
def test_inputs_keep_foreign_key_no_exposed_relationship_sets(
    decorator: str, model: type[DeclarativeBase], kwargs: dict[str, Any]
) -> None:
    """Test that a foreign key column is part of mutation inputs when no relationship they expose sets it."""
    assert "fruit_id" in _input_field_names(decorator, model, **kwargs)


@pytest.mark.parametrize("decorator", _MUTATION_INPUT_DECORATORS)
@pytest.mark.parametrize("model", [_Sticker, _Badge])
def test_inputs_exclude_foreign_key_set_by_exposed_relationship(decorator: str, model: type[DeclarativeBase]) -> None:
    """Test that a foreign key column is left out of mutation inputs exposing the relationship setting it."""
    fields = _input_field_names(decorator, model, include="all")
    assert "fruit_id" not in fields
    assert "fruit" in fields


def test_nested_create_input_excludes_foreign_key_set_by_parent_relationship() -> None:
    """Test that nested create inputs leave out the foreign key set by the parent relationship."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.type(_Fruit, include="all")
    class FruitType: ...

    @strawchemy.create_input(_Fruit, include="all")
    class FruitCreate: ...

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_fruit: FruitType = strawchemy.create(FruitCreate)

    schema = strawberry.Schema(query=Query, mutation=Mutation)
    for nested_input in ("_Fruit_FruitLabelInput", "_Fruit_StickerInput"):
        type_definition = schema.get_type_by_name(nested_input)
        assert isinstance(type_definition, StrawberryObjectDefinition)
        assert "fruit_id" not in {field.name for field in type_definition.fields}


@pytest.mark.parametrize(("color_model", "fruit_model"), [(Color, Fruit), (ColorDataclass, FruitDataclass)])
def test_add_non_input_relationships(
    color_model: type[Color | ColorDataclass], fruit_model: type[Fruit | FruitDataclass]
) -> None:
    strawchemy = Strawchemy("postgresql")

    @strawchemy.create_input(color_model, include="all")
    class ColorInput: ...

    color = ColorInput(name="Blue")  # ty: ignore[unknown-argument]
    color_input = Input(color)
    assert len(color_input.relations) == 0
    color_input.instances[0].fruits.append(fruit_model(name="Apple", color_id=uuid4(), sweetness=1, color=None))
    color_input.add_non_input_relations()
    assert len(color_input.relations) == 1


@pytest.mark.parametrize("include", [["basket_id", "label", "name"], ["name"], "all"])
def test_pk_update_input_keeps_foreign_key_primary_key(include: FieldSpec) -> None:
    """Test that a primary key column that is also a foreign key is part of the update-by-ids input."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.pk_update_input(_BasketItem, include=include)
    class BasketItemUpdate: ...

    fields = {field.name: field for field in get_object_definition(BasketItemUpdate, strict=True).fields}
    assert {"basket_id", "label", "name"} <= fields.keys()
    assert fields["basket_id"].type is int


def test_pk_update_input_excludes_relation_writing_primary_key() -> None:
    """Test that the update-by-ids input leaves out a to-one relation whose local columns belong to the key."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.pk_update_input(_BasketItem, include="all")
    class BasketItemUpdate: ...

    assert "basket" not in {field.name for field in get_object_definition(BasketItemUpdate, strict=True).fields}


@pytest.mark.parametrize("decorator", ["create_input", "filter_update_input"])
def test_non_pk_update_inputs_exclude_foreign_key_primary_key(decorator: str) -> None:
    """Test that inputs not identifying rows by key leave out a primary key column that is also a foreign key."""
    strawchemy = Strawchemy("postgresql")

    @getattr(strawchemy, decorator)(_BasketItem, include="all")
    class BasketItemInput: ...

    fields = {field.name for field in get_object_definition(BasketItemInput, strict=True).fields}
    assert "basket_id" not in fields
    assert {"label", "name", "basket"} <= fields
