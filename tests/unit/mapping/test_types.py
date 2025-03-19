from __future__ import annotations

import textwrap
from importlib import import_module
from typing import TYPE_CHECKING, Any

import pytest
from strawchemy.exceptions import StrawchemyError
from strawchemy.graphql.exceptions import InspectorError
from strawchemy.strawberry.exceptions import StrawchemyFieldError

import strawberry
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry import auto
from strawberry.scalars import JSON
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition
from syrupy.assertion import SnapshotAssertion
from tests.unit.models import Book as BookModel
from tests.unit.models import User

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
    from tests.unit.schemas.resolver.custom_resolver import ColorType, Query

    schema = strawberry.Schema(query=Query)
    type_def = schema.get_type_by_name("FruitType")
    assert isinstance(type_def, StrawberryObjectDefinition)
    field = type_def.get_field("color")
    assert field
    assert field.type is ColorType


@pytest.mark.parametrize(
    "path",
    [pytest.param("tests.unit.schemas.override.auto_type_existing", id="auto_type_existing")],
)
def test_multiple_types_error(path: str) -> None:
    with pytest.raises(
        StrawchemyError,
        match=(
            """Type `FruitType` cannot be auto generated because it's already declared."""
            """ You may want to set `override=True` on the existing type to use it everywhere."""
        ),
    ):
        import_module(path)


def test_aggregation_type_mismatch() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=(
            """The `color_aggregations` field is defined with `root_aggregations` enabled but the field type is not a root aggregation type."""
        ),
    ):
        import_module("tests.unit.schemas.aggregations.type_mismatch")


def test_base_array_fails() -> None:
    with pytest.raises(
        InspectorError,
        match=("""Base SQLAlchemy ARRAY type is not supported. Use backend-specific array type instead."""),
    ):
        import_module("tests.unit.schemas.filters.filters_base_array")


def test_base_json_fails() -> None:
    with pytest.raises(
        InspectorError,
        match=("""Base SQLAlchemy JSON type is not supported. Use backend-specific json type instead."""),
    ):
        import_module("tests.unit.schemas.filters.filters_base_json")


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("include.all_fields.Query", id="all_fields"),
        pytest.param("include.all_fields_override.Query", id="all_fields_override"),
        pytest.param("include.all_fields_filter.Query", id="all_fields_with_filter"),
        pytest.param("include.all_order_by.Query", id="all_fields_order_by"),
        pytest.param("include.include_explicit.Query", id="include_explicit"),
        pytest.param("include.include_non_existent.Query", id="include_non_existent"),
        pytest.param("exclude.exclude_explicit.Query", id="exclude_explicit"),
        pytest.param("exclude.exclude_non_existent.Query", id="exclude_non_existent"),
        pytest.param("exclude.exclude_and_override_type.Query", id="exclude_and_override_type"),
        pytest.param("exclude.exclude_and_override_field.Query", id="exclude_and_override_field"),
        pytest.param("resolver.primary_key_resolver.Query", id="primary_key_resolver"),
        pytest.param("resolver.list_resolver.Query", id="list_resolver"),
        pytest.param("override.override_argument.Query", id="argument_override"),
        pytest.param("override.override_auto_type.Query", id="override_auto_type"),
        pytest.param("override.override_with_custom_name.Query", id="override_with_custom_name"),
        pytest.param("pagination.pagination.Query", id="pagination"),
        pytest.param("pagination.pagination_defaults.Query", id="pagination_defaults"),
        pytest.param("pagination.children_pagination.Query", id="children_pagination"),
        pytest.param("pagination.children_pagination_defaults.Query", id="children_pagination_defaults"),
        pytest.param("pagination.pagination_default_limit.Query", id="pagination_default_limit"),
        pytest.param("pagination.pagination_config_default.Query", id="pagination_config_default"),
        pytest.param("custom_id_field_name.Query", id="custom_id_field_name"),
        pytest.param("enums.Query", id="enums"),
        pytest.param("filters.filters.Query", id="filters"),
        pytest.param("filters.filters_aggregation.Query", id="aggregation_filters"),
        pytest.param("aggregations.root_aggregations.Query", id="root_aggregations"),
    ],
)
@pytest.mark.snapshot
def test_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    module, query_name = f"tests.unit.schemas.{path}".rsplit(".", maxsplit=1)
    query_class = getattr(import_module(module), query_name)

    schema = strawberry.Schema(query=query_class, scalar_overrides={dict[str, Any]: JSON})
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


@pytest.mark.parametrize(
    "path", [pytest.param("geo.geo_filters.Query", id="geo_filters"), pytest.param("geo.geo.Query", id="geo_type")]
)
@pytest.mark.geo
@pytest.mark.snapshot
def test_geo_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    from geoalchemy2 import WKBElement, WKTElement
    from strawchemy.strawberry.geo import GeoJSON

    module, query_name = f"tests.unit.schemas.{path}".rsplit(".", maxsplit=1)
    query_class = getattr(import_module(module), query_name)

    schema = strawberry.Schema(
        query=query_class, scalar_overrides={dict[str, Any]: JSON, WKTElement: GeoJSON, WKBElement: GeoJSON}
    )
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


@pytest.mark.parametrize("path", [pytest.param("input_type.Mutation", id="input_type")])
@pytest.mark.snapshot
def test_mutation_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    module, query_name = f"tests.unit.schemas.mutations.{path}".rsplit(".", maxsplit=1)
    mutation_class = getattr(import_module(module), query_name)

    @strawberry.type
    class Query:
        @strawberry.field
        def hello(self) -> str:
            return "world"

    schema = strawberry.Schema(query=Query, mutation=mutation_class, scalar_overrides={dict[str, Any]: JSON})
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot
