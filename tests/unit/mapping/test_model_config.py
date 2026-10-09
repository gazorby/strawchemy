from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID  # noqa: TC003  # resolved at runtime from the relay node annotations

import pytest
import strawberry
from strawberry import relay
from strawberry.types import get_object_definition
from strawberry.types.base import StrawberryList, has_object_definition

from strawchemy.utils.strawberry import strawberry_contained_user_type
from tests.unit.models import Color, Fruit, User

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy

TYPE_DECORATOR_NAMES: list[str] = ["type", "aggregate", "filter", "aggregate_filter", "order"]


@pytest.mark.parametrize("decorator", TYPE_DECORATOR_NAMES)
def test_type_no_purpose_excluded(decorator: str, strawchemy: Strawchemy) -> None:
    @getattr(strawchemy, decorator)(User, include="all", override=True)
    class UserType: ...

    type_def = get_object_definition(UserType, strict=True)
    assert type_def.get_field("private") is None


@pytest.mark.parametrize("decorator", ["create_input", "pk_update_input", "filter_update_input"])
def test_type_no_purpose_excluded_input(decorator: str, strawchemy: Strawchemy) -> None:
    @getattr(strawchemy, decorator)(User, include="all")
    class UserType: ...

    type_def = get_object_definition(UserType, strict=True)
    assert type_def.get_field("private") is None


def _print_schema(**fields: type[Any]) -> str:
    query = strawberry.type(type("Query", (), {"__annotations__": fields}))
    return str(strawberry.Schema(query=query))


class _ShoutMixin:
    def shout(self) -> str:
        return "mixin"


def test_identical_type_keeps_user_bases(strawchemy: Strawchemy) -> None:
    """Test that a type sharing the config of an earlier one still inherits from its own bases."""

    @strawchemy.type(Fruit, include="all")
    class FruitType: ...

    @strawchemy.type(Fruit, include="all")
    class MixinFruitType(_ShoutMixin): ...

    assert issubclass(MixinFruitType, _ShoutMixin)
    assert MixinFruitType.shout(cast("Any", None)) == "mixin"
    assert not issubclass(FruitType, _ShoutMixin)


def test_identical_type_keeps_class_body(strawchemy: Strawchemy) -> None:
    """Test that a type sharing the config of an earlier one still keeps its own methods."""

    @strawchemy.type(Fruit, include="all")
    class FruitType: ...

    @strawchemy.type(Fruit, include="all")
    class HelperFruitType:
        def helper(self) -> str:
            return "helper"

    assert HelperFruitType.helper(cast("Any", None)) == "helper"
    assert not hasattr(FruitType, "helper")


def test_identical_type_keeps_own_resolvers(strawchemy: Strawchemy) -> None:
    """Test that a type sharing the config of an earlier one gets its own resolvers, not the earlier ones."""

    @strawchemy.type(Fruit, include="all")
    class FruitType:
        @strawberry.field
        def first(self) -> int:
            return 1

    @strawchemy.type(Fruit, include="all")
    class OtherFruitType:
        @strawberry.field
        def second(self) -> int:
            return 2

    other_definition = get_object_definition(OtherFruitType, strict=True)

    assert get_object_definition(FruitType, strict=True).get_field("first") is not None
    assert other_definition.get_field("second") is not None
    assert other_definition.get_field("first") is None


def test_identical_filter_keeps_boolean_field_names(strawchemy: Strawchemy) -> None:
    """Test that a filter sharing the config of an earlier one keeps the GraphQL names of its boolean fields."""

    @strawchemy.filter(Fruit, include="all")
    class FruitFilter: ...

    @strawchemy.filter(Fruit, include="all")
    class OtherFruitFilter: ...

    def graphql_names(filter_type: type[Any]) -> dict[str, str | None]:
        return {
            field.python_name: field.graphql_name
            for field in get_object_definition(filter_type, strict=True).fields
            if field.python_name in {"and_", "or_", "not_"}
        }

    expected = {"and_": "_and", "or_": "_or", "not_": "_not"}

    assert graphql_names(FruitFilter) == expected
    assert graphql_names(OtherFruitFilter) == expected


def test_identical_relay_node_types(strawchemy: Strawchemy) -> None:
    """Test that a relay node sharing the config of an earlier one still inherits from Node."""

    @strawchemy.type(Fruit, include=["name"])
    class FruitNode(relay.Node):
        id: relay.NodeID[UUID]

    @strawchemy.type(Fruit, include=["name"])
    class OtherFruitNode(relay.Node):
        id: relay.NodeID[UUID]

        @classmethod
        def custom(cls) -> str:
            return "custom"

    assert issubclass(FruitNode, relay.Node)
    assert issubclass(OtherFruitNode, relay.Node)
    assert OtherFruitNode.custom() == "custom"


def test_identical_type_relations_use_first_type(strawchemy: Strawchemy) -> None:
    """Test that relations reuse the first declared type when a later one shares its config."""

    @strawchemy.type(Fruit, include="all")
    class FruitType: ...

    @strawchemy.type(Fruit, include="all")
    class OtherFruitType(_ShoutMixin): ...

    @strawchemy.type(Color, include="all")
    class ColorWithFruitsType: ...

    fruits_field = get_object_definition(ColorWithFruitsType, strict=True).get_field("fruits")

    assert fruits_field is not None
    assert isinstance(fruits_field.type, StrawberryList)
    assert fruits_field.type.of_type is FruitType
    schema = _print_schema(color=ColorWithFruitsType, fruit=FruitType, other_fruit=OtherFruitType)
    assert "type FruitType {" in schema
    assert "type OtherFruitType {" in schema


def test_identical_order_keeps_resolved_relations(strawchemy: Strawchemy) -> None:
    """Test that an order type sharing a cached config keeps the relation types the cache resolved."""

    @strawchemy.type(Color, include="all", order="all")
    class ColorType: ...

    @strawchemy.order(Fruit, include="all")
    class FruitOrderBy: ...

    @strawchemy.order(Color, include="all")
    class ColorOrder: ...

    fruits_field = get_object_definition(ColorOrder, strict=True).get_field("fruits")

    assert fruits_field is not None
    assert has_object_definition(strawberry_contained_user_type(fruits_field.type))
