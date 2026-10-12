from __future__ import annotations

from datetime import datetime  # noqa: TC003  # resolved at runtime by SQLAlchemy
from importlib.util import find_spec
from typing import Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import Column, ForeignKey, Integer, Sequence, Table, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import get_object_definition
from strawberry.types.base import StrawberryObjectDefinition, StrawberryOptional

from strawchemy import Strawchemy, StrawchemyConfig
from strawchemy.dto.types import FieldSpec
from strawchemy.exceptions import DTOError
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


class _GeneratedValuesBase(DeclarativeBase):
    pass


class _Item(_GeneratedValuesBase):
    __tablename__ = "item"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=func.now())


class _Parent(_GeneratedValuesBase):
    __tablename__ = "parent"

    id: Mapped[int] = mapped_column(Integer, Sequence("parent_id_seq", optional=False), primary_key=True)
    name: Mapped[str]
    children: Mapped[list[_Child]] = relationship("_Child", back_populates="parent")


class _Child(_GeneratedValuesBase):
    __tablename__ = "child"

    id: Mapped[int] = mapped_column(Integer, Sequence("child_id_seq", optional=False), primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("parent.id"))
    name: Mapped[str]
    a: Mapped[str]
    parent: Mapped[_Parent] = relationship(_Parent, back_populates="children")


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


@pytest.mark.parametrize(
    "config",
    [
        {"include": ["basket_id", "label", "basket"]},
        {"include": ["basket"]},
        {"include": "all", "type_map": {"basket": int}},
    ],
)
def test_pk_update_input_rejects_explicit_relation_writing_primary_key(config: dict[str, Any]) -> None:
    """Test that explicitly requesting a to-one relation writing the key in an update-by-ids input raises."""
    strawchemy = Strawchemy("postgresql")

    with pytest.raises(DTOError, match=r"_BasketItem\.basket writes primary key column basket_id"):

        @strawchemy.pk_update_input(_BasketItem, **config)
        class BasketItemUpdate: ...


def test_pk_update_input_rejects_annotated_relation_writing_primary_key() -> None:
    """Test that annotating a to-one relation writing the key on an update-by-ids input raises."""
    strawchemy = Strawchemy("postgresql")

    with pytest.raises(DTOError, match=r"_BasketItem\.basket writes primary key column basket_id"):

        @strawchemy.pk_update_input(_BasketItem, include="all")
        class BasketItemUpdate:
            basket: int | None


@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_pk_update_rejects_explicit_relation_writing_primary_key() -> None:
    """Test that the pydantic update-by-ids model raises on an explicitly included relation writing the key."""
    strawchemy = Strawchemy("postgresql")

    with pytest.raises(DTOError, match=r"_BasketItem\.basket writes primary key column basket_id"):

        @strawchemy.pydantic.pk_update(_BasketItem, include=["basket_id", "label", "basket"])
        class BasketItemUpdate: ...


@pytest.mark.parametrize("decorator", ["create_input", "filter_update_input"])
def test_non_pk_update_inputs_exclude_foreign_key_primary_key(decorator: str) -> None:
    """Test that inputs not identifying rows by key leave out a primary key column that is also a foreign key."""
    strawchemy = Strawchemy("postgresql")

    @getattr(strawchemy, decorator)(_BasketItem, include="all")
    class BasketItemInput: ...

    fields = {field.name for field in get_object_definition(BasketItemInput, strict=True).fields}
    assert "basket_id" not in fields
    assert {"label", "name", "basket"} <= fields


@pytest.mark.parametrize("decorator", ["create_input", "filter_update_input"])
def test_non_pk_update_inputs_keep_explicit_relation_writing_primary_key(decorator: str) -> None:
    """Test that inputs not identifying rows by key accept an explicitly included relation writing the key."""
    strawchemy = Strawchemy("postgresql")

    @getattr(strawchemy, decorator)(_BasketItem, include=["label", "basket"])
    class BasketItemInput: ...

    assert "basket" in {field.name for field in get_object_definition(BasketItemInput, strict=True).fields}


def _optional_fields(definition: StrawberryObjectDefinition) -> dict[str, bool]:
    return {field.name: isinstance(field.type, StrawberryOptional) for field in definition.fields}


def _nested_child_input_fields(root: type[Any]) -> dict[str, bool]:
    def create(_data: Any) -> int:
        return 1

    create.__annotations__ = {"_data": root, "return": int}

    @strawberry.type
    class Query:
        create_parent: int = strawberry.field(resolver=create)

    nested_input = strawberry.Schema(query=Query).get_type_by_name("_Parent_ChildInput")
    assert isinstance(nested_input, StrawberryObjectDefinition)
    return _optional_fields(nested_input)


@pytest.mark.parametrize("include", ["all", ["id", "name", "created_at"]])
def test_create_input_makes_database_generated_values_optional(include: FieldSpec) -> None:
    """Test that create inputs make generated primary keys and SQL-expression defaults optional, however included."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.create_input(_Item, include=include)
    class ItemCreate: ...

    assert _optional_fields(get_object_definition(ItemCreate, strict=True)) == {
        "id": True,
        "name": False,
        "created_at": True,
    }


@pytest.mark.parametrize("include", ["all", ["name", "children"], ["id", "name", "children"]])
def test_nested_create_input_makes_database_generated_values_optional(include: FieldSpec) -> None:
    """Test that nested create inputs make generated primary keys optional whatever the root includes."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.create_input(_Parent, include=include)
    class ParentCreate: ...

    assert _nested_child_input_fields(ParentCreate) == {"id": True, "name": False, "a": False}


@pytest.mark.parametrize("declare_other_first", [False, True])
def test_nested_create_input_ignores_other_root_include(declare_other_first: bool) -> None:
    """Test that a nested create input does not depend on the include of another root declared before it."""
    strawchemy = Strawchemy("postgresql")

    if declare_other_first:

        @strawchemy.create_input(_Parent, include="all")
        class ParentAll: ...

    @strawchemy.create_input(_Parent, include=["name", "children"])
    class ParentSome: ...

    assert _nested_child_input_fields(ParentSome) == {"id": True, "name": False, "a": False}


@pytest.mark.parametrize("declare_other_first", [False, True])
def test_nested_create_input_ignores_other_root_aliases(declare_other_first: bool) -> None:
    """Test that a nested create input does not take the field aliases of another root declared before it."""
    strawchemy = Strawchemy("postgresql")

    if declare_other_first:

        @strawchemy.create_input(_Parent, include="all")
        class ParentAliased:
            label: str = strawchemy.field(model_field="name")

    @strawchemy.create_input(_Parent, include="all")
    class ParentPlain: ...

    assert _nested_child_input_fields(ParentPlain).keys() == {"id", "name", "a"}


@pytest.mark.xfail(strict=True, reason="Root include='all' widens shared nested inputs, see #484")
def test_nested_create_input_ignores_other_root_include_all() -> None:
    """Test that another root's include="all" does not widen a nested input built under a narrower config include."""
    strawchemy = Strawchemy(StrawchemyConfig("postgresql", include=["id", "name"]))

    @strawchemy.create_input(_Parent, include="all")
    class ParentAll: ...

    @strawchemy.create_input(_Parent, include=["name", "children"])
    class ParentSome: ...

    assert _nested_child_input_fields(ParentSome).keys() == {"id", "name"}
