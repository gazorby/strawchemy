from __future__ import annotations

import dataclasses as dc
import re
import textwrap
from datetime import timedelta
from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from strawberry import auto
from strawberry.scalars import JSON
from strawberry.schema.types.scalar import DEFAULT_SCALAR_REGISTRY
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition

from strawchemy import RELATIONSHIPS, SCALARS
from strawchemy.exceptions import EmptyDTOError, QueryHookError, StrawchemyError, StrawchemyFieldError
from strawchemy.schema.scalars import Interval
from strawchemy.testing.pytest_plugin import MockContext
from tests.fixtures import DefaultQuery
from tests.unit.models import Book as BookModel
from tests.unit.models import Color, Fruit, User
from tests.utils import DTOInspect

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy.mapper import Strawchemy

SCALAR_OVERRIDES: dict[object, Any] = {dict[str, Any]: DEFAULT_SCALAR_REGISTRY[JSON], timedelta: Interval}


def test_type_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_override_same_name_does_not_leak_fields(strawchemy: Strawchemy) -> None:
    """The last override wins when used with the same model/name pair.

    A second `override=True` registration under the same GraphQL type name must
    reflect its own (narrower) config, not inherit fields from the earlier
    registration.
    """
    from tests.unit.models import Color, Fruit

    @strawchemy.type(Fruit, name="FruitNode", include=["id"], override=True)
    class FruitNode:
        pass

    @strawchemy.type(Color, name="ColorNode", include=["id", "name", "fruits"], override=True)
    class ColorWide:
        pass

    @strawchemy.type(Color, name="ColorNode", include=["id"], override=True)
    class ColorSlim:
        pass

    wide_fields = {f.name for f in ColorWide.__strawberry_definition__.fields}
    slim_fields = {f.name for f in ColorSlim.__strawberry_definition__.fields}

    assert wide_fields == {"fruits_aggregate", "fruits", "id", "name"}
    assert slim_fields == {"id"}


def test_type_instance_auto_as_str(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


def test_input_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.create_input(User)
    class InputType:
        id: auto
        name: auto

    user = InputType(id=1, name="user")
    assert user.id == 1
    assert user.name == "user"


@pytest.mark.parametrize(
    ("decorator", "default_value"),
    [
        pytest.param("type", "anon", id="type"),
        pytest.param("order", "anon", id="order"),
        pytest.param("filter", "anon", id="filter"),
        pytest.param("create_input", "anon", id="create_input"),
        pytest.param("pk_update_input", "anon", id="pk_update_input"),
        pytest.param("filter_update_input", "anon", id="filter_update_input"),
    ],
)
def test_class_body_literal_defaults_preserved(strawchemy: Strawchemy, decorator: str, default_value: Any) -> None:
    """User-written class-body literal defaults survive every row-shaped strawchemy decorator."""

    @getattr(strawchemy, decorator)(Fruit, include=["name", "sweetness"])
    class FruitTestType:
        name: str | None = default_value

    fields = {f.name: f for f in FruitTestType.__strawberry_definition__.fields}
    assert fields["name"].default == default_value, FruitTestType.__name__
    # Fields without a class-body default keep their generated default
    assert {f.name: f for f in FruitTestType.__strawberry_definition__.fields}["sweetness"].default in (
        dc.MISSING,
        strawberry.UNSET,
    )
    # The literal default applies when instantiating the type
    assert FruitTestType(sweetness=1).name == default_value


@pytest.mark.parametrize(
    ("decorator", "default_value"),
    [
        pytest.param("aggregate", "anon", id="filter_update_input"),
        pytest.param("aggregate_filter", "anon", id="filter_update_input"),
    ],
)
def test_class_body_literal_defaults_preserved_aggregate(
    strawchemy: Strawchemy, decorator: str, default_value: Any
) -> None:
    @getattr(strawchemy, decorator)(Fruit, include=["name", "sweetness"])
    class FruitTestType:
        name: str | None = default_value

    fields = {f.name: f for f in FruitTestType.__strawberry_definition__.fields}
    assert fields["name"].default == default_value, FruitTestType.__name__


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
    with pytest.raises(StrawchemyError, match=re.escape("Type `FruitType` is already registered")):
        import_module(path)


def test_aggregation_type_mismatch() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape(
            """The `color_aggregations` field is defined with `root_aggregations` enabled but the field type is not a root aggregation type."""
        ),
    ):
        import_module("tests.unit.schemas.aggregations.type_mismatch")


def test_query_hooks_wrong_relationship_load_spec() -> None:
    with pytest.raises(
        QueryHookError, match=re.escape("Keys of mappings passed in `load` param must be relationship attributes: ")
    ):
        import_module("tests.unit.schemas.query_hooks")


def test_excluding_pk_from_update_input_fail() -> None:
    with pytest.raises(
        StrawchemyError,
        match=re.escape(
            "You cannot exclude primary key columns from an input type intended for create or update mutations"
        ),
    ):
        import_module("tests.unit.schemas.mutations.invalid_pk_update_input")


def test_read_only_pk_on_update_input_fail() -> None:
    with pytest.raises(
        EmptyDTOError,
        match=re.escape(
            "Cannot generate `NewGroupUsersIdFieldsInput` input type from `NewUser` model because primary key columns are disabled for write purpose"
        ),
    ):
        import_module("tests.unit.schemas.mutations.read_only_pk_with_update_input")


def test_delete_mutation_type_not_list_fail() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape("Type of delete mutation must be a list: delete_group"),
    ):
        import_module("tests.unit.schemas.mutations.delete_mutation_type_not_list")


def test_update_mutation_by_filter_type_not_list_fail() -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape("Type of update mutation by filter must be a list: update_groups"),
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
        pytest.param("resolver.class_body_resolver_override.Query", id="class_body_resolver_override"),
        pytest.param("override.override_argument.Query", id="argument_override"),
        pytest.param("override.override_auto_type.Query", id="override_auto_type"),
        pytest.param("override.override_with_custom_name.Query", id="override_with_custom_name"),
        pytest.param("override.nested_overrides.Query", id="nested_overrides"),
        pytest.param("pagination.pagination.Query", id="pagination"),
        pytest.param("pagination.pagination_defaults.Query", id="pagination_defaults"),
        pytest.param("pagination.children_pagination.Query", id="children_pagination"),
        pytest.param("pagination.children_pagination_defaults.Query", id="children_pagination_defaults"),
        pytest.param("pagination.pagination_config_default.Query", id="pagination_config_default"),
        pytest.param("pagination.pagination_default_limit.Query", id="pagination_default_limit"),
        pytest.param("pagination.pagination_default_offset.Query", id="pagination_default_offset"),
        pytest.param("pagination.paginate_specific_fields.Query", id="paginate_specific_fields"),
        pytest.param("pagination.paginate_empty.Query", id="paginate_empty"),
        pytest.param("pagination.pagination_config_empty.Query", id="pagination_config_empty"),
        pytest.param("pagination.pagination_config_specific_fields.Query", id="pagination_config_specific_fields"),
        pytest.param(
            "pagination.pagination_config_with_type_override.Query", id="pagination_config_with_type_override"
        ),
        pytest.param("pagination.paginate_and_order_combined.Query", id="paginate_and_order_combined"),
        pytest.param("pagination.paginate_all_with_default.Query", id="paginate_all_with_default"),
        pytest.param("custom_id_field_name.Query", id="custom_id_field_name"),
        pytest.param("enums.Query", id="enums"),
        pytest.param("filters.filters.Query", id="filters"),
        pytest.param("filters.filters_aggregation.Query", id="aggregation_filters"),
        pytest.param("filters.type_filter.Query", id="type_filter"),
        pytest.param("filters.field_filter_auto_generate.Query", id="field_filter_auto_generate"),
        pytest.param("order.type_order_by.Query", id="type_order_by"),
        pytest.param("order.field_order_by.Query", id="field_order_by"),
        pytest.param("order.field_order_by_all.Query", id="field_order_by_all"),
        pytest.param("order.field_order_by_specific_fields.Query", id="field_order_by_specific_fields"),
        pytest.param("order.order_config_all.Query", id="order_config_all"),
        pytest.param(
            "order.order_config_specific_fields_with_type_override.Query",
            id="order_config_specific_fields_with_type_override",
        ),
        pytest.param(
            "order.order_config_empty_with_empty_type_override.Query", id="order_config_empty_with_empty_type_override"
        ),
        pytest.param("order.order_config_all_with_field_override.Query", id="order_config_all_with_field_override"),
        pytest.param("order.order_config_specific_fields.Query", id="order_config_specific_fields"),
        pytest.param("order.order_config_empty.Query", id="order_config_empty"),
        pytest.param("order.order_config_with_field_override.Query", id="order_config_with_field_override"),
        pytest.param("order.type_order_by_specific_fields.Query", id="type_order_by_specific_fields"),
        pytest.param("aggregations.root_aggregations.Query", id="root_aggregations"),
        pytest.param("distinct.type_distinct_manual_enum.Query", id="type_distinct_manual_enum"),
        pytest.param("distinct.distinct_config_all.Query", id="distinct_config_all"),
        pytest.param("distinct.field_distinct_all.Query", id="field_distinct_all"),
        pytest.param("distinct.field_distinct_specific_fields.Query", id="field_distinct_specific_fields"),
        pytest.param("distinct.distinct_config_with_field_override.Query", id="distinct_config_with_field_override"),
        pytest.param("distinct.distinct_config_specific_fields.Query", id="distinct_config_specific_fields"),
        pytest.param("distinct.distinct_config_empty.Query", id="distinct_config_empty"),
        pytest.param("scope.schema_before.Query", id="scope_schema_before"),
        pytest.param("scope.schema_after.Query", id="scope_schema_after"),
        pytest.param("scope.schema_middle.Query", id="scope_schema_middle"),
        pytest.param("lazy.query.Query", id="lazy_circular_default_scope"),
        pytest.param("lazy_global.query.Query", id="lazy_circular_global_scope"),
        pytest.param("forwardref.query.Query", id="forwardref_circular_default_scope"),
        pytest.param("forwardref_global.query.Query", id="forwardref_circular_global_scope"),
        pytest.param("union_override_lazy.Query", id="union_override_lazy"),
        pytest.param("union_override_plain.Query", id="union_override_plain"),
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
    from strawchemy.schema.scalars.geo import GEO_SCALAR_OVERRIDES

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
        pytest.param("create_no_id.Mutation", id="create_no_id"),
        pytest.param("upsert.Mutation", id="upsert"),
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
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_validation(query: str, name: str, is_list: bool) -> None:
    from tests.unit.schemas.pydantic.validation import Mutation

    schema = strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES)
    result = schema.execute_sync(query, context_value=MockContext("postgresql"))
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


@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
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
    result = schema.execute_sync(query, context_value=MockContext("postgresql"))
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


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("schema_after", id="scope-after"),
        pytest.param("schema_before", id="scope-before"),
        pytest.param("schema_middle", id="scope-middle"),
    ],
)
def test_schema_scope_override(module_name: str) -> None:
    """Test schema scope is working properly no matter where the override is declared."""
    query_class = import_module(f"tests.unit.schemas.scope.{module_name}").Query

    schema = strawberry.Schema(query=query_class, scalar_overrides=SCALAR_OVERRIDES)
    schemas_str = textwrap.dedent(str(schema)).strip()

    assert "GroupType" not in schemas_str
    assert "GraphQLGroup" in schemas_str


def test_json_column_class_body_resolver_executes() -> None:
    """The overridden `dict_col` resolver runs and returns its own value, not the JSON projection (#161)."""
    from tests.unit.schemas.resolver.class_body_resolver_override import ExecutableQuery

    schema = strawberry.Schema(query=ExecutableQuery, scalar_overrides=SCALAR_OVERRIDES)
    result = schema.execute_sync("{ overriddenJson { dictCol } }")
    assert not result.errors
    assert result.data == {"overriddenJson": {"dictCol": "OVERRIDE"}}


def test_exclude_relationships_avoids_stub_collision(strawchemy: Strawchemy) -> None:
    """Test that exclude=[RELATIONSHIPS] walks no relationships, so a later explicit type for a related model does not collide with a pre-registered walker stub (#162)."""

    # First slice scopes Fruit with a relationship-free walk...
    @strawchemy.type(Fruit, exclude=[RELATIONSHIPS])
    class FruitNode:
        pass

    # ...so a later explicit Color type must NOT collide with a walker stub.
    @strawchemy.type(Color, include=[SCALARS])
    class ColorNode:
        pass

    fruit_fields = set(DTOInspect(FruitNode).annotations())
    assert "color" not in fruit_fields
    assert {"id", "name", "sweetness", "color_id"} <= fruit_fields
