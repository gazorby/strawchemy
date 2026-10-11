import sys
from importlib import import_module
from typing import ForwardRef, Optional

import pytest
import strawberry
from strawberry.types.object_type import StrawberryObjectDefinition

from strawchemy.utils.annotation import get_annotations, get_type_hints_partial

pytestmark = pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 649 lazy annotations need Python 3.14+")


def test_get_annotations_keeps_undefined_names_as_forward_refs() -> None:
    """Test that a lazy annotation naming an undefined type is read as a forward reference."""

    class Child:
        name: str
        missing: NotDefinedYet  # noqa: F821  # ty: ignore[unresolved-reference]

    annotations = get_annotations(Child)

    assert annotations["name"] is str
    assert isinstance(annotations["missing"], ForwardRef)
    assert annotations["missing"].__forward_arg__ == "NotDefinedYet"


def test_get_type_hints_partial_keeps_undefined_names_as_forward_refs() -> None:
    """Test that an undefined name stays a forward reference while the other lazy annotations resolve."""

    class Parent:
        parent_id: int

    class Child(Parent):
        name: str | None
        missing: list[NotDefinedYet]  # noqa: F821  # ty: ignore[unresolved-reference]

    type_hints = get_type_hints_partial(Child)

    assert type_hints["parent_id"] is int
    assert type_hints["name"] == Optional[str]
    (missing,) = type_hints["missing"].__args__
    assert isinstance(missing, ForwardRef)
    assert missing.__forward_arg__ == "NotDefinedYet"


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("late_type_lazy.relation_annotation", id="same_module"),
        pytest.param("late_type_lazy.relation_annotation_private", id="with_private_field"),
    ],
)
def test_lazy_relation_annotation_resolves_type_defined_after_it(module: str) -> None:
    """Test that a lazy relation annotation naming a later-defined type resolves once that type exists."""
    schema_module = import_module(f"tests.unit.schemas.{module}")

    schema = strawberry.Schema(query=schema_module.Query)
    fruit_type = schema.get_type_by_name("FruitType")
    assert isinstance(fruit_type, StrawberryObjectDefinition)
    color = fruit_type.get_field("color")
    assert color is not None
    assert color.type is schema_module.ColorType
    name = fruit_type.get_field("name")
    assert name is not None
    assert name.type is str
    assert "secret: " not in str(schema)
