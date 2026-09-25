from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument

from strawchemy import StrawchemyAsyncRepository
from strawchemy.constants import RESPONSE_VALUES_ATTRIBUTE

if TYPE_CHECKING:
    from strawberry import Info

    from strawchemy.mapper import Strawchemy
    from strawchemy.schema.field import StrawchemyField


def _nested_field(strawchemy: Strawchemy, *, with_argument: bool) -> StrawchemyField:
    arguments = (
        [StrawberryArgument("limit", None, type_annotation=StrawberryAnnotation(int), default=1)]
        if with_argument
        else None
    )
    field = strawchemy.field(root_field=False, repository_type=StrawchemyAsyncRepository, arguments=arguments)
    field.python_name = "fruits"
    return field


def _info(response_key: str) -> Info[Any, Any]:
    return cast("Info[Any, Any]", SimpleNamespace(path=SimpleNamespace(key=response_key)))


def test_nested_field_with_arguments_is_not_basic(strawchemy: Strawchemy) -> None:
    """Test that a nested field taking arguments is resolved with its info, while one without stays basic."""
    assert not _nested_field(strawchemy, with_argument=True).is_basic_field
    assert _nested_field(strawchemy, with_argument=False).is_basic_field


def test_nested_field_is_sync_with_async_repository(strawchemy: Strawchemy) -> None:
    """Test that a nested field reads its value synchronously even when its repository is async."""
    assert not _nested_field(strawchemy, with_argument=True).is_async


def test_nested_field_resolves_value_of_its_response_key(strawchemy: Strawchemy) -> None:
    """Test that a nested field given its arguments returns the value stored for its alias, else its attribute."""
    field = _nested_field(strawchemy, with_argument=True)
    source = SimpleNamespace(fruits="first", **{RESPONSE_VALUES_ATTRIBUTE: {"a": "first", "b": "second"}})
    assert field.get_result(source, _info("b"), [], {"limit": 2}) == "second"
    assert field.get_result(source, _info("fruits"), [], {"limit": 2}) == "first"
    assert field.get_result(SimpleNamespace(fruits="plain"), _info("b"), [], {"limit": 2}) == "plain"
