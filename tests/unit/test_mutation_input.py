from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from strawchemy.dto.types import FieldSpec
from strawchemy.schema.mutation import Input
from tests.unit.dc_models import ColorDataclass, FruitDataclass
from tests.unit.models import Color, Fruit


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
