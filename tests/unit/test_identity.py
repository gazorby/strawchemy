from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar, ForwardRef, Optional

import pytest
import strawberry
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from strawchemy.dto.identity import TypeIdentityCache, shape_key
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.exceptions import ScopeConflictError
from tests.unit.models import Color, Fruit


def _generated(type_name: str, annotations: dict[str, Any], /, **attributes: Any) -> type[Any]:
    return type(type_name, (), {"__annotations__": annotations, "__dto_model__": Fruit, **attributes})


@strawberry.type(name="RegisteredType")
class _Registered:
    __dto_model__: ClassVar[type[Any]] = Fruit
    name: str


class _Plain:
    pass


class _Field:
    def __init__(self, model_field_name: str) -> None:
        self.model_field_name = model_field_name


_NameFields = Enum("_NameFields", [("name", _Field("name"))])
_LabelFields = Enum("_LabelFields", [("name", _Field("label"))])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param({"name": str}, {"name": str}, id="same-annotation"),
        pytest.param({"__dto_config__": ClassVar[object], "name": str}, {"name": str}, id="dunder-annotations-ignored"),
        pytest.param({"color": ForwardRef("ColorType")}, {"color": "ColorType"}, id="forward-ref-and-string"),
        pytest.param(
            {"color": Optional[ForwardRef("ColorType")]},  # ty: ignore[invalid-type-form]
            {"color": Optional[_generated("ColorType", {})]},  # ty: ignore[invalid-type-form]
            id="forward-ref-and-generated-class",
        ),
        pytest.param({"other": _Registered}, {"other": ForwardRef("RegisteredType")}, id="registered-name"),
    ],
)
def test_equal_shapes_are_reused(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Test that a generated type of the same name and shape as an earlier one is replaced by it."""
    cache = TypeIdentityCache()
    earlier = _generated("FruitOrderBy", first)

    assert cache.canonical("kind", "FruitOrderBy", earlier) is earlier
    assert cache.canonical("kind", "FruitOrderBy", _generated("FruitOrderBy", second)) is earlier


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(
            _generated("FruitOrderBy", {"name": str}), _generated("FruitOrderBy", {"id": str}), id="field-names"
        ),
        pytest.param(
            _generated("FruitOrderBy", {"name": str}, name=None),
            _generated("FruitOrderBy", {"name": str}, name="default"),
            id="default",
        ),
        pytest.param(
            _generated("FruitOrderBy", {"name": str}, name=strawberry.field(description="first")),
            _generated("FruitOrderBy", {"name": str}, name=strawberry.field(description="second")),
            id="field-description",
        ),
        pytest.param(
            _generated("FruitOrderBy", {"name": str}, name=strawberry.field(default_factory=list)),
            _generated("FruitOrderBy", {"name": str}, name=strawberry.field(default_factory=dict)),
            id="field-default-factory",
        ),
        pytest.param(
            _generated("FruitOrderBy", {"other": _Plain}),
            _generated("FruitOrderBy", {"other": type("_Plain", (), {})}),
            id="plain-classes-by-identity",
        ),
    ],
)
def test_different_shapes_are_kept(first: type[Any], second: type[Any]) -> None:
    """Test that a generated type exposing something else than an earlier one of its name is kept."""
    cache = TypeIdentityCache()
    cache.canonical("kind", "FruitOrderBy", first)

    assert cache.canonical("kind", "FruitOrderBy", second) is second


def test_kind_and_name_separate_equal_shapes() -> None:
    """Test that equal shapes of another kind or name are not reused."""
    cache = TypeIdentityCache()
    earlier = _generated("FruitOrderBy", {"name": str})
    cache.canonical("kind", "FruitOrderBy", earlier)

    assert cache.canonical("other", "FruitOrderBy", same_kind := _generated("FruitOrderBy", {"name": str})) is same_kind
    assert (
        cache.canonical("kind", "ColorOrderBy", other_name := _generated("ColorOrderBy", {"name": str})) is other_name
    )


def test_enum_shape_holds_members_and_their_fields() -> None:
    """Test that an enum shape lists its members with the model field each one stands for."""
    assert shape_key(_NameFields) == ("enum", (("name", "name"),))
    assert shape_key(_NameFields) != shape_key(_LabelFields)


def test_second_scope_claim_raises() -> None:
    """Test that claiming a schema scope another declaration holds raises."""
    cache = TypeIdentityCache()
    cache.claim_scope("scope", "ColorType", _Plain, Color)
    cache.declare_scope("scope", _Registered)

    assert cache.stand_in("scope") is _Registered
    assert cache.scoped_name("scope") == "ColorType"
    with pytest.raises(ScopeConflictError, match="cannot declare the schema scope"):
        cache.claim_scope("scope", "OtherColorType", _Plain, Color)


@pytest.mark.parametrize("no_cache", [False, True])
def test_generated_request_of_another_description_is_kept(no_cache: bool) -> None:
    """Test that a generated input requested again with another description is a type of its own."""
    strawchemy = Strawchemy("postgresql")
    config = DTOConfig(Purpose.READ, include=["name"])

    def make_input(description: str) -> type[Any]:
        return strawchemy.filter_factory.make_input(
            Fruit, mode="filter", dto_config=config, description=description, no_cache=no_cache
        )

    first, second = make_input("first"), make_input("second")

    assert first is not second
    assert get_object_definition(second, strict=True).description == "second"
