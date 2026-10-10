"""No postponed annotations: evaluated and quoted ClassVar annotations are tested separately."""

from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from tests.unit.models import Color

Decorator = Callable[[Strawchemy], Callable[[type[Any]], type[Any]]]

DECORATORS: list[Decorator] = [
    lambda sc: sc.type(Color, include="all"),
    lambda sc: sc.create_input(Color, include="all"),
    lambda sc: sc.pk_update_input(Color, include="all"),
    lambda sc: sc.filter_update_input(Color, include="all"),
    lambda sc: sc.filter(Color, include="all"),
    lambda sc: sc.order(Color, include="all"),
]
DECORATOR_IDS = ["type", "create_input", "pk_update_input", "filter_update_input", "filter", "order"]


class _KindMixin:
    kind: ClassVar[str] = "color"


def _graphql_field_names(type_: type[Any]) -> set[str]:
    return {field.python_name for field in get_object_definition(type_, strict=True).fields}


@pytest.mark.parametrize("decorator", DECORATORS, ids=DECORATOR_IDS)
def test_classvar_with_default(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a ClassVar with a default stays a class attribute and is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType:
        kind: ClassVar[str] = "color"

    assert ColorType.kind == "color"
    assert "kind" not in _graphql_field_names(ColorType)


@pytest.mark.parametrize("decorator", DECORATORS, ids=DECORATOR_IDS)
def test_classvar_on_mixin(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a ClassVar inherited from a plain mixin stays a class attribute and is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType(_KindMixin): ...

    assert ColorType.kind == "color"
    assert "kind" not in _graphql_field_names(ColorType)


@pytest.mark.parametrize("decorator", DECORATORS, ids=DECORATOR_IDS)
def test_classvar_without_default(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a ClassVar without a default is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType:
        kind: ClassVar[str]

    assert "kind" not in _graphql_field_names(ColorType)


@pytest.mark.parametrize("decorator", DECORATORS, ids=DECORATOR_IDS)
def test_string_classvar(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a string-annotated ClassVar stays a class attribute and is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType:
        kind: "ClassVar[str]" = "color"

    assert ColorType.kind == "color"
    assert "kind" not in _graphql_field_names(ColorType)


@pytest.mark.parametrize("decorator", DECORATORS[:4], ids=DECORATOR_IDS[:4])
def test_unresolvable_string_classvar(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a string ClassVar whose type hints cannot be resolved is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType:
        kind: "ClassVar[Undefined]" = "color"  # noqa: F821  # ty: ignore[unresolved-reference]  # must not resolve

    assert ColorType.kind == "color"
    assert "kind" not in _graphql_field_names(ColorType)


def test_classvar_shadowing_model_field_is_not_a_type_override(strawchemy: Strawchemy) -> None:
    """Test that a ClassVar named after a model field neither overrides nor removes that field."""

    @strawchemy.type(Color, include="all")
    class ColorType:
        name: ClassVar[int] = 1

    name_field = next(
        field for field in get_object_definition(ColorType, strict=True).fields if field.python_name == "name"
    )
    assert name_field.type is str
