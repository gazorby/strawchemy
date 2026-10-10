"""Postponed annotations: ClassVar annotations reach strawchemy as strings, quoted ones with their quotes."""

from __future__ import annotations

from typing import ClassVar

import pytest

from strawchemy import Strawchemy
from tests.unit.mapping.test_classvar import DECORATOR_IDS, DECORATORS, Decorator, graphql_field_names


@pytest.mark.parametrize("decorator", DECORATORS[:4], ids=DECORATOR_IDS[:4])
def test_unresolvable_classvar(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a ClassVar whose type hints cannot be resolved is not a GraphQL field."""

    @decorator(strawchemy)
    class ColorType:
        kind: ClassVar[Undefined] = "color"  # noqa: F821  # ty: ignore[unresolved-reference]  # must not resolve

    assert ColorType.kind == "color"
    assert "kind" not in graphql_field_names(ColorType)


@pytest.mark.parametrize("decorator", DECORATORS[:4], ids=DECORATOR_IDS[:4])
def test_unresolvable_quoted_classvar(strawchemy: Strawchemy, decorator: Decorator) -> None:
    """Test that a quoted ClassVar whose type hints cannot be resolved is not a GraphQL field."""
    # Built dynamically: pyupgrade strips the quotes from a literal `kind: "ClassVar[...]"` annotation.
    namespace = {"__module__": __name__, "__annotations__": {"kind": "'ClassVar[Undefined]'"}, "kind": "color"}
    color_type = decorator(strawchemy)(type("ColorType", (), namespace))

    assert color_type.kind == "color"
    assert "kind" not in graphql_field_names(color_type)
