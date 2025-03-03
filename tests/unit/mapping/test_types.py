from __future__ import annotations

import textwrap
from importlib import import_module
from typing import TYPE_CHECKING, Any

import pytest
from strawchemy.exceptions import StrawchemyError
from syrupy.assertion import SnapshotAssertion

import strawberry
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry import auto
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition
from tests.models import Book as BookModel
from tests.models import User

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy
    from syrupy.assertion import SnapshotAssertion


def test_type_instance(strawchemy: Strawchemy[DeclarativeBase, QueryableAttribute[Any]]) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_type_instance_auto_as_str(strawchemy: Strawchemy[DeclarativeBase, QueryableAttribute[Any]]) -> None:
    @strawchemy.type(User)
    class UserType:
        id: "auto"
        name: "auto"

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_input_instance(strawchemy: Strawchemy[DeclarativeBase, QueryableAttribute[Any]]) -> None:
    @strawchemy.input(User)
    class InputType:
        id: auto
        name: auto

    user = InputType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_field_metadata_default(strawchemy: Strawchemy[DeclarativeBase, QueryableAttribute[Any]]) -> None:
    """Test metadata default.

    Test that textual metadata from the SQLAlchemy model isn't reflected in the Strawberry
    type by default.
    """

    @strawchemy.type(BookModel)
    class Book:
        title: auto

    type_def = get_object_definition(Book, strict=True)
    assert type_def.description == "GraphQL type"
    title_field = type_def.get_field("title")
    assert title_field is not None
    assert title_field.description is None


def test_type_resolution_with_resolvers() -> None:
    from tests.schemas.custom_resolver import ColorType, Query

    schema = strawberry.Schema(query=Query)
    type_def = schema.get_type_by_name("FruitType")
    assert isinstance(type_def, StrawberryObjectDefinition)
    field = type_def.get_field("color")
    assert field
    assert field.type is ColorType


def test_multiple_types_error() -> None:
    with pytest.raises(
        StrawchemyError,
        match=(
            """Type `FruitType` cannot be auto generated because it's already explicitly declared."""
            """ Either use `override=True` on the explicit type to use it everywhere, or use override `FruitType` fields where needed"""
        ),
    ):
        from tests.schemas import multiple_types  # noqa: F401 # pyright: ignore[reportUnusedImport]


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("tests.schemas.all_fields.Query", id="all_fields"),
        pytest.param("tests.schemas.all_fields_override.Query", id="all_fields_override"),
        pytest.param("tests.schemas.all_fields_filter.Query", id="all_fields_with_filter"),
        pytest.param("tests.schemas.all_order_by.Query", id="all_fields_order_by"),
        pytest.param("tests.schemas.include_explicit.Query", id="include_explicit"),
        pytest.param("tests.schemas.exclude_explicit.Query", id="exclude_explicit"),
        pytest.param("tests.schemas.include_non_existent.Query", id="include_non_existent"),
        pytest.param("tests.schemas.exclude_non_existent.Query", id="exclude_non_existent"),
        pytest.param("tests.schemas.primary_key_resolver.Query", id="primary_key_resolver"),
        pytest.param("tests.schemas.list_resolver.Query", id="list_resolver"),
        pytest.param("tests.schemas.exclude_and_override_type.Query", id="exclude_and_override_type"),
        pytest.param("tests.schemas.exclude_and_override_field.Query", id="exclude_and_override_field"),
        pytest.param("tests.schemas.type_override.Query", id="type_override"),
        pytest.param("tests.schemas.pagination.Query", id="pagination"),
        pytest.param("tests.schemas.pagination_defaults.Query", id="pagination_defaults"),
        pytest.param("tests.schemas.child_pagination.Query", id="child_pagination"),
        pytest.param("tests.schemas.child_pagination_defaults.Query", id="child_pagination_defaults"),
        pytest.param("tests.schemas.pagination_config_defaults.Query", id="pagination_config_defaults"),
        pytest.param("tests.schemas.custom_id_field_name.Query", id="custom_id_field_name"),
    ],
)
def test_schemas(path: str, snapshot: SnapshotAssertion) -> None:
    module, query_name = path.rsplit(".", maxsplit=1)
    query_class = getattr(import_module(module), query_name)

    schema = strawberry.Schema(query=query_class)
    assert textwrap.dedent(str(schema)).strip() == snapshot
