from __future__ import annotations

import re
import warnings
from importlib import import_module
from typing import TYPE_CHECKING

import pytest

from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.field import StrawchemyField
from tests.unit.models import Color, Fruit

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy


def _make_class(**fields: object) -> type:
    namespace = dict(fields)
    namespace["__annotations__"] = dict.fromkeys(fields, str)
    return type("Probe", (), namespace)


def test_field_stores_model_field(strawchemy: Strawchemy) -> None:
    """Test that `field(model_field=...)` stores the target and marks the field non-root."""
    field = strawchemy.field(model_field="name")
    assert isinstance(field, StrawchemyField)
    assert field.model_field == "name"
    # A mapped leaf is not a root field.
    assert field.is_root_field is False


def test_field_model_field_defaults_to_none(strawchemy: Strawchemy) -> None:
    """Test that `model_field` is None when not provided to `field()`."""
    field = strawchemy.field()
    assert field.model_field is None


def test_model_field_forces_non_root_even_when_root_field_true(strawchemy: Strawchemy) -> None:
    """Test that `model_field` overrides an explicit `root_field=True` to non-root."""
    field = strawchemy.field(model_field="name", root_field=True)
    assert field.is_root_field is False


def test_collect_builds_alias_delta(strawchemy: Strawchemy) -> None:
    """Test that the collector maps a model field name to its declared schema name."""
    probe = _make_class(full_name=strawchemy.field(model_field="name"))
    delta = strawchemy.type_factory.collect_field_model_aliases(probe, Fruit, DTOConfig(Purpose.READ))
    assert delta == {"name": "full_name"}


def test_collect_ignores_plain_fields(strawchemy: Strawchemy) -> None:
    """Test that fields without a `model_field` produce no alias entry."""
    probe = _make_class(plain=strawchemy.field())
    delta = strawchemy.type_factory.collect_field_model_aliases(probe, Fruit, DTOConfig(Purpose.READ))
    assert delta == {}


def test_collect_missing_model_field_raises(strawchemy: Strawchemy) -> None:
    """Test that targeting a non-existent model field raises `StrawchemyFieldError`."""
    probe = _make_class(full_name=strawchemy.field(model_field="does_not_exist"))
    with pytest.raises(StrawchemyFieldError, match="does_not_exist"):
        strawchemy.type_factory.collect_field_model_aliases(probe, Fruit, DTOConfig(Purpose.READ))


def test_collect_duplicate_target_raises(strawchemy: Strawchemy) -> None:
    """Test that two schema fields targeting the same model field raise `StrawchemyFieldError`."""
    probe = _make_class(
        full_name=strawchemy.field(model_field="name"),
        other_name=strawchemy.field(model_field="name"),
    )
    with pytest.raises(StrawchemyFieldError, match="name"):
        strawchemy.type_factory.collect_field_model_aliases(probe, Fruit, DTOConfig(Purpose.READ))


def test_collect_schema_name_shadowing_other_model_field_raises(strawchemy: Strawchemy) -> None:
    """Test that a schema name shadowing a different model column raises `StrawchemyFieldError`."""
    # `sweetness` is itself a real Fruit column; using it as the schema name while
    # pointing model_field at a different column must error, not silently mis-resolve.
    probe = _make_class(sweetness=strawchemy.field(model_field="name"))
    with pytest.raises(StrawchemyFieldError, match="shadows"):
        strawchemy.type_factory.collect_field_model_aliases(probe, Fruit, DTOConfig(Purpose.READ))


def test_type_renames_field_to_schema_name(strawchemy: Strawchemy) -> None:
    """Test that `model_field` on a type renames the model column and keeps it linked."""

    @strawchemy.type(Fruit)
    class FruitType:
        full_name: str = strawchemy.field(model_field="name")

    field_names = {f.name for f in FruitType.__strawberry_definition__.fields}
    assert "full_name" in field_names
    # The original model field name is not exposed.
    assert "name" not in field_names
    # The schema field must be genuinely linked to the model column `name`,
    # not an unlinked standalone field.
    field_defs = FruitType.__dto_field_definitions__
    assert "full_name" in field_defs
    assert field_defs["full_name"].model_field_name == "name"


def test_type_declared_annotation_overrides_inferred_type(strawchemy: Strawchemy) -> None:
    """Test that a declared annotation overrides the aliased column's inferred type."""

    @strawchemy.type(Fruit)
    class FruitType:
        sweetness_label: str = strawchemy.field(model_field="sweetness")  # sweetness is int on the model

    field = next(f for f in FruitType.__strawberry_definition__.fields if f.name == "sweetness_label")
    # The declared `str` annotation wins over the model's int column type.
    assert field.type is str
    # The schema field is genuinely linked to the model column `sweetness`.
    assert FruitType.__dto_field_definitions__["sweetness_label"].model_field_name == "sweetness"


def test_input_maps_and_round_trips(strawchemy: Strawchemy) -> None:
    """Test that `model_field` on an input renames the field and round-trips via `to_mapped()`."""

    @strawchemy.input(Fruit, mode="create_input")
    class FruitCreate:
        full_name: str = strawchemy.field(model_field="name")
        sweetness: int

    field_names = {f.name for f in FruitCreate.__strawberry_definition__.fields}
    assert "full_name" in field_names
    assert "name" not in field_names

    instance = FruitCreate(full_name="apple", sweetness=3)
    mapped = instance.to_mapped()
    assert mapped.name == "apple"
    # The input field definition links back to the real model column.
    assert FruitCreate.__dto_field_definitions__["full_name"].model_field_name == "name"


def test_model_field_maps_relationship(strawchemy: Strawchemy) -> None:
    """Test that `model_field` renames a relationship field and keeps it linked."""

    @strawchemy.type(Fruit)
    class FruitType:
        name: str

    @strawchemy.type(Color)
    class ColorType:
        items: list[FruitType] = strawchemy.field(model_field="fruits")

    field_names = {f.name for f in ColorType.__strawberry_definition__.fields}
    assert "items" in field_names
    assert "fruits" not in field_names
    assert ColorType.__dto_field_definitions__["items"].model_field_name == "fruits"


def test_missing_model_field_raises_on_import() -> None:
    """Test that a missing `model_field` target raises at decoration (import) time."""
    with pytest.raises(StrawchemyFieldError, match=re.escape("Model field 'nope' not found on Fruit")):
        import_module("tests.unit.schemas.model_field.missing_model_field")


def test_duplicate_target_raises_on_import() -> None:
    """Test that duplicate `model_field` targets raise at decoration (import) time."""
    with pytest.raises(StrawchemyFieldError, match=re.escape("targeted by multiple schema fields")):
        import_module("tests.unit.schemas.model_field.duplicate_target")


def test_type_aliases_param_deprecated(strawchemy: Strawchemy) -> None:
    """Test that the type-level `aliases=` param still renames but emits a deprecation warning."""
    with pytest.warns(DeprecationWarning, match="model_field"):

        @strawchemy.type(Fruit, aliases={"name": "full_name"}, include={"name"})
        class FruitType:
            pass

    field_names = {f.name for f in FruitType.__strawberry_definition__.fields}
    assert "full_name" in field_names
    assert "name" not in field_names
    assert FruitType.__dto_field_definitions__["full_name"].model_field_name == "name"


def test_input_aliases_param_deprecated(strawchemy: Strawchemy) -> None:
    """Test that the input-level `aliases=` param still renames but emits a deprecation warning."""
    with pytest.warns(DeprecationWarning, match="model_field"):

        @strawchemy.input(Fruit, mode="create_input", aliases={"name": "full_name"}, include={"name", "sweetness"})
        class FruitCreate:
            pass

    field_names = {f.name for f in FruitCreate.__strawberry_definition__.fields}
    assert "full_name" in field_names
    assert "name" not in field_names

    mapped = FruitCreate(full_name="apple", sweetness=3).to_mapped()
    assert mapped.name == "apple"


def test_alias_generator_not_deprecated(strawchemy: Strawchemy) -> None:
    """Test that the `alias_generator=` param renames fields without a deprecation warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @strawchemy.type(Fruit, alias_generator=str.upper, include={"name"})
        class FruitType:
            pass

    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]
    field_names = {f.name for f in FruitType.__strawberry_definition__.fields}
    assert "NAME" in field_names


def test_type_level_aliases_declared_annotation_overrides_inferred_type(strawchemy: Strawchemy) -> None:
    """Test that a declared annotation overrides the inferred type on the deprecated `aliases=` path."""
    # A divergent body annotation on a field renamed via the deprecated `aliases=`
    # param still overrides the column's inferred type (consistent with model_field).
    with pytest.warns(DeprecationWarning, match="model_field"):

        @strawchemy.type(Fruit, aliases={"sweetness": "sweetness_label"})
        class FruitType:
            sweetness_label: str  # `sweetness` is an int column on the model

    field = next(f for f in FruitType.__strawberry_definition__.fields if f.name == "sweetness_label")
    assert field.type is str
    assert FruitType.__dto_field_definitions__["sweetness_label"].model_field_name == "sweetness"
