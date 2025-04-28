from __future__ import annotations

import textwrap
from datetime import timedelta
from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

import pytest
from strawchemy.dto.exceptions import EmptyDTOError
from strawchemy.exceptions import StrawchemyError
from strawchemy.graphql.exceptions import InspectorError
from strawchemy.sqlalchemy.exceptions import QueryHookError
from strawchemy.strawberry.exceptions import StrawchemyFieldError
from strawchemy.strawberry.scalars import Interval
from strawchemy.testing.pytest_plugin import MockContext

import strawberry
from strawberry import auto
from strawberry.scalars import JSON
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition
from syrupy.assertion import SnapshotAssertion
from tests.fixtures import DefaultQuery
from tests.unit.models import Book as BookModel
from tests.unit.models import User

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy

    from syrupy.assertion import SnapshotAssertion


SCALAR_OVERRIDES: dict[object, Any] = {dict[str, Any]: JSON, timedelta: Interval}


def test_type_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_type_instance_auto_as_str(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: "auto"
        name: "auto"

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_input_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.create_input(User)
    class InputType:
        id: auto
        name: auto

    user = InputType(id=1, name="user")  # pyright: ignore[reportCallIssue]
    assert user.id == 1  # pyright: ignore[reportAttributeAccessIssue]
    assert user.name == "user"  # pyright: ignore[reportAttributeAccessIssue]


def test_field_metadata_default(strawchemy: Strawchemy) -> None:
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


def test_base_array_fail() -> None:
    with pytest.raises(
        InspectorError,
        match=("""Base SQLAlchemy ARRAY type is not supported. Use backend-specific array type instead."""),
    ):
        import_module("tests.unit.schemas.filters.filters_base_array")


def test_base_json_fail() -> None:
    with pytest.raises(
        InspectorError,
        match=("""Base SQLAlchemy JSON type is not supported. Use backend-specific json type instead."""),
    ):
        import_module("tests.unit.schemas.filters.filters_base_json")


def test_query_hooks_wrong_relationship_load_spec() -> None:
    with pytest.raises(
        QueryHookError, match=("Keys of mappings passed in `load` param must be relationship attributes: ")
    ):
        import_module("tests.unit.schemas.query_hooks")


def test_excluding_pk_from_update_input_fail() -> None:
    with pytest.raises(
        StrawchemyError,
        match=("""You cannot exclude primary key columns from an input type intended for create or update mutations"""),
    ):
        import_module("tests.unit.schemas.mutations.invalid_pk_update_input")


def test_read_only_pk_on_update_input_fail() -> None:
    with pytest.raises(
        EmptyDTOError,
        match=(
            "Cannot generate `NewGroupUsersIdFieldsInput` input type from `NewUser` model because primary key columns are disabled for write purpose"
        ),
    ):
        import_module("tests.unit.schemas.mutations.read_only_pk_with_update_input")


def test_delete_mutation_type_not_list_fail() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=("Type of delete mutation must be a list: delete_group"),
    ):
        import_module("tests.unit.schemas.mutations.delete_mutation_type_not_list")


def test_update_mutation_by_filter_type_not_list_fail() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=("Type of update mutation by filter must be a list: update_groups"),
    ):
        import_module("tests.unit.schemas.mutations.invalid_filter_update_field")


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
        pytest.param("override.nested_overrides.Query", id="nested_overrides"),
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
        pytest.param("filters.type_filter.Query", id="type_filter"),
        pytest.param("order.type_order_by.Query", id="type_order_by"),
        pytest.param("order.field_order_by.Query", id="field_order_by"),
        pytest.param("order.auto_order_by.Query", id="auto_order_by"),
        pytest.param("aggregations.root_aggregations.Query", id="root_aggregations"),
        pytest.param("distinct.Query", id="distinct"),
    ],
)
@pytest.mark.snapshot
def test_query_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    module, query_name = f"tests.unit.schemas.{path}".rsplit(".", maxsplit=1)
    query_class = getattr(import_module(module), query_name)

    schema = strawberry.Schema(query=query_class, scalar_overrides=SCALAR_OVERRIDES)
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


@pytest.mark.parametrize(
    "path", [pytest.param("geo.geo_filters.Query", id="geo_filters"), pytest.param("geo.geo.Query", id="geo_type")]
)
@pytest.mark.geo
@pytest.mark.snapshot
@pytest.mark.skipif(not find_spec("geoalchemy2"), reason="geoalchemy2 is not installed")
def test_geo_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    from strawchemy.strawberry.geo import GEO_SCALAR_OVERRIDES

    module, query_name = f"tests.unit.schemas.{path}".rsplit(".", maxsplit=1)
    query_class = getattr(import_module(module), query_name)

    schema = strawberry.Schema(query=query_class, scalar_overrides=(SCALAR_OVERRIDES | GEO_SCALAR_OVERRIDES))
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("create.Mutation", id="create_mutation"),
        pytest.param("update.Mutation", id="update_mutation"),
        pytest.param("delete.Mutation", id="delete_mutation"),
    ],
)
@pytest.mark.snapshot
def test_mutation_schemas(path: str, graphql_snapshot: SnapshotAssertion) -> None:
    module, query_name = f"tests.unit.schemas.mutations.{path}".rsplit(".", maxsplit=1)
    mutation_class = getattr(import_module(module), query_name)

    @strawberry.type
    class Query:
        @strawberry.field
        def hello(self) -> str:
            return "world"

    schema = strawberry.Schema(query=Query, mutation=mutation_class, scalar_overrides=SCALAR_OVERRIDES)
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


@pytest.mark.snapshot
def test_query_and_mutations(graphql_snapshot: SnapshotAssertion) -> None:
    from tests.unit.schemas.mutation_and_query import Mutation, Query

    schema = strawberry.Schema(query=Query, mutation=Mutation)
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


def test_field_filter_equals_type_filter() -> None:
    from tests.unit.schemas.filters.filters import Query as FieldFilterQuery
    from tests.unit.schemas.filters.type_filter import Query as TypeFilterQuery

    field_filter_schema = strawberry.Schema(query=FieldFilterQuery, scalar_overrides=SCALAR_OVERRIDES)
    type_filter_schema = strawberry.Schema(query=TypeFilterQuery, scalar_overrides=SCALAR_OVERRIDES)

    assert textwrap.dedent(str(field_filter_schema)).strip() == textwrap.dedent(str(type_filter_schema)).strip()


def test_field_order_by_equals_type_order_by() -> None:
    from tests.unit.schemas.order.field_order_by import Query as FieldOrderQuery
    from tests.unit.schemas.order.type_order_by import Query as TypeOrderQuery

    field_filter_schema = strawberry.Schema(query=FieldOrderQuery, scalar_overrides=SCALAR_OVERRIDES)
    type_filter_schema = strawberry.Schema(query=TypeOrderQuery, scalar_overrides=SCALAR_OVERRIDES)

    assert textwrap.dedent(str(field_filter_schema)).strip() == textwrap.dedent(str(type_filter_schema)).strip()


@pytest.mark.parametrize(
    ("query", "name", "is_list"),
    [
        pytest.param(
            """
            mutation {
                createUser(
                    data: {
                        name: "Bob",
                        group: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } },
                        tag: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } }
                    }
                ) {
                    __typename
                    ... on UserType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            "createUser",
            False,
            id="create",
        ),
        pytest.param(
            """
            mutation {
                createUserCustom(
                    data: {
                        name: "Bob",
                        group: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } },
                        tag: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } }
                    }
                ) {
                    __typename
                    ... on UserType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            "createUserCustom",
            False,
            id="create-custom",
        ),
        pytest.param(
            """
            mutation {
                updateUsers(
                    filter: { id: { eq: "da636751-b276-4546-857f-3c73ea914467" } },
                    data: { name: "Bob" }
                ) {
                    __typename
                    ... on UserType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            "updateUsers",
            True,
            id="update_by_filter",
        ),
        pytest.param(
            """
            mutation {
                updateUserByIds(
                    data: [
                        {
                            id: "da636751-b276-4546-857f-3c73ea914467",
                            name: "Bob"
                        }
                    ]
                ) {
                    __typename
                    ... on UserType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            "updateUserByIds",
            True,
            id="update_by_ids",
        ),
        pytest.param(
            """
            mutation {
                updateUserById(
                    data: {
                        id: "da636751-b276-4546-857f-3c73ea914467",
                        name: "Bob"
                    }
                ) {
                    __typename
                    ... on UserType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            "updateUserById",
            False,
            id="update_by_id",
        ),
    ],
)
def test_pydantic_validation(query: str, name: str, is_list: bool) -> None:
    from tests.unit.schemas.pydantic.validation import Mutation

    schema = strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES)
    result = schema.execute_sync(query, context_value=MockContext())
    assert not result.errors
    assert result.data

    error = result.data[name][0] if is_list else result.data[name]
    assert error["__typename"] == "ValidationErrorType"
    assert error["id"] == "ERROR"
    assert error["errors"] == [
        {
            "id": "ERROR",
            "loc": ["name"],
            "message": "Value error, Name must be lower cased",
            "type": "value_error",
        }
    ]


def test_pydantic_validation_nested() -> None:
    from tests.unit.schemas.pydantic.validation import Mutation

    query = """
        mutation {
            createUser(
                data: {
                    name: "bob",
                    tag: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } }
                    group: {
                        create: {
                            name: "Group",
                            tag: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } },
                            color: { set: { id: "da636751-b276-4546-857f-3c73ea914467" } }
                        }
                    }
                }
            ) {
                __typename
                ... on UserType {
                    name
                }
                ... on ValidationErrorType {
                    id
                    errors {
                        id
                        loc
                        message
                        type
                    }
                }
            }
        }
    """
    schema = strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES)
    result = schema.execute_sync(query, context_value=MockContext())
    assert not result.errors
    assert result.data

    assert result.data["createUser"]["__typename"] == "ValidationErrorType"
    assert result.data["createUser"]["id"] == "ERROR"
    assert result.data["createUser"]["errors"] == [
        {
            "id": "ERROR",
            "loc": ["group", "name"],
            "message": "Value error, Name must be lower cased",
            "type": "value_error",
        }
    ]
