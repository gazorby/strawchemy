from __future__ import annotations

import dataclasses as dc
import re
import textwrap
import warnings
from datetime import timedelta
from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

import pytest
import strawberry
from graphql import (
    GraphQLEnumType,
    GraphQLInputField,
    GraphQLInputObjectType,
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLSchema,
    build_schema,
    get_named_type,
)
from strawberry import auto, relay
from strawberry.scalars import JSON
from strawberry.schema.types.scalar import DEFAULT_SCALAR_REGISTRY
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition

from strawchemy import RELATIONSHIPS, SCALARS, Strawchemy, StrawchemyConfig
from strawchemy.exceptions import (
    EmptyDTOError,
    QueryHookError,
    ReadOnlyModelError,
    ScopeConflictError,
    StrawchemyError,
    StrawchemyFieldError,
    TypeNameConflictError,
)
from strawchemy.schema.scalars import Interval
from strawchemy.utils.strawberry import strawberry_contained_user_type
from tests.fixtures import DefaultQuery
from tests.unit.models import Album, Color, Container, Department, Fruit, Group, TableMappedFruit, Tag, User
from tests.unit.models import Book as BookModel
from tests.unit.schemas.join_mapped import JoinedAB, JoinOwner
from tests.unit.schemas.join_mapped_columns import ColumnJoinOwner
from tests.unit.utils import MockContext
from tests.utils import DTOInspect

if TYPE_CHECKING:
    from collections.abc import Callable

    from syrupy.assertion import SnapshotAssertion
    from typing_extensions import Self

    from strawchemy.dto.types import FieldSpec
    from strawchemy.schema.factories.base import TypeScope
    from strawchemy.typing import SupportedDialect

SCALAR_OVERRIDES: dict[object, Any] = {dict[str, Any]: DEFAULT_SCALAR_REGISTRY[JSON], timedelta: Interval}
JOIN_MAPPED_ERROR_TEMPLATE = (
    "{} is mapped onto a join or a selectable, not a table: mutations and write inputs are not supported"
)
JOIN_MAPPED_ERROR = re.escape(JOIN_MAPPED_ERROR_TEMPLATE.format("JoinedAB"))


def _field_type(type_definition: StrawberryObjectDefinition, name: str) -> Any:
    field = type_definition.get_field(name)
    assert field is not None
    return strawberry_contained_user_type(field.type)


def test_type_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")  # ty: ignore[unknown-argument]
    assert user.id == 1
    assert user.name == "user"


def test_type_implementing_interface() -> None:
    """Test that a type inheriting a strawberry interface becomes an object type implementing it once."""
    from tests.unit.schemas.interface.implements_interface import FruitType, Named

    definition = get_object_definition(FruitType, strict=True)

    assert definition.name == "FruitType"
    assert not definition.is_interface
    assert definition.interfaces == [get_object_definition(Named, strict=True)]


def test_type_instance_auto_as_str(strawchemy: Strawchemy) -> None:
    @strawchemy.type(User)
    class UserType:
        id: auto
        name: auto

    user = UserType(id=1, name="user")  # ty: ignore[unknown-argument]
    assert user.id == 1
    assert user.name == "user"


def test_input_instance(strawchemy: Strawchemy) -> None:
    @strawchemy.create_input(User)
    class InputType:
        id: auto
        name: auto

    user = InputType(id=1, name="user")  # ty: ignore[unknown-argument]
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


def test_declaration_named_like_a_generated_type_takes_its_name() -> None:
    """Test that a declaration named like a type generated before it takes the name, the generated type being renamed."""
    module = import_module("tests.unit.schemas.override.auto_type_existing")
    color_fruits = get_object_definition(module.ColorType, strict=True).get_field("fruits")
    assert color_fruits is not None

    assert get_object_definition(module.FruitType, strict=True).name == "FruitType"
    assert strawberry_contained_user_type(color_fruits.type) is not module.FruitType


def _declare(strawchemy: Strawchemy, decorator: str, model: type[Any], kwargs: dict[str, Any]) -> type[Any]:
    @getattr(strawchemy, decorator)(model, **kwargs)
    class Declared: ...

    return Declared


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(
            ("create_input", User, {"include": ["name"], "name": "UserInput"}),
            ("pk_update_input", User, {"include": ["name"], "name": "UserInput"}),
            id="create-and-pk-update-input-name",
        ),
        pytest.param(
            ("create_input", User, {"include": ["name"]}),
            ("pk_update_input", User, {"include": ["name"]}),
            id="create-and-pk-update-input",
        ),
        pytest.param(
            ("create_input", User, {"include": ["name"]}),
            ("filter_update_input", User, {"include": ["name"]}),
            id="create-and-filter-update-input",
        ),
        pytest.param(
            ("create_input", User, {"include": ["name"]}),
            ("create_input", User, {"include": ["id", "name"]}),
            id="create-input",
        ),
        pytest.param(("filter", User, {"include": ["name"]}), ("filter", User, {"include": ["id"]}), id="filter"),
        pytest.param(("order", User, {"include": ["name"]}), ("order", User, {"include": ["id"]}), id="order"),
        pytest.param(
            ("filter", User, {"include": ["name"]}), ("filter", Group, {"include": ["name"]}), id="filter-models"
        ),
        pytest.param(
            ("order", User, {"include": ["name"]}), ("order", Group, {"include": ["name"]}), id="order-models"
        ),
        pytest.param(
            ("distinct_on", User, {"include": ["name"]}), ("distinct_on", User, {"include": ["id"]}), id="distinct-on"
        ),
        pytest.param(
            ("distinct_on", User, {"include": ["name"]}),
            ("distinct_on", Group, {"include": ["name"]}),
            id="distinct-on-models",
        ),
        pytest.param(
            ("upsert_update_fields", User, {"include": ["name"]}),
            ("upsert_update_fields", User, {"include": ["id"]}),
            id="upsert-update-fields",
        ),
        pytest.param(
            ("upsert_update_fields", User, {"include": ["name"]}),
            ("upsert_update_fields", Group, {"include": ["name"]}),
            id="upsert-update-fields-models",
        ),
        pytest.param(
            ("upsert_conflict_fields", User, {}),
            ("upsert_conflict_fields", Group, {}),
            id="upsert-conflict-fields-models",
        ),
    ],
)
def test_same_named_declarations_error(
    strawchemy: Strawchemy,
    first: tuple[str, type[Any], dict[str, Any]],
    second: tuple[str, type[Any], dict[str, Any]],
) -> None:
    """Test that a declaration registered under the name of a different one declared before raises, naming both."""
    _declare(strawchemy, *first)
    origins = rf"`[\w.]+` \(model `{first[1].__name__}`\) conflicts with `[\w.]+` \(model `{second[1].__name__}`\)"
    with pytest.raises(TypeNameConflictError, match=rf"^Type `\w+` is already registered: {origins}$"):
        _declare(strawchemy, *second)


def _declaration_and_relation_argument_schema(
    decorator: str, name: str, field_kwarg: str, *, declared_first: bool
) -> str:
    strawchemy = Strawchemy(StrawchemyConfig("postgresql", order_by="all", distinct_on="all"))

    def declare() -> type[Any]:
        return getattr(strawchemy, decorator)(Fruit, include=["name"])(type(name, (), {}))

    declared = declare() if declared_first else None

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    if declared is None:
        declared = declare()

    @strawchemy.type(Fruit, include="all")
    class FruitNode: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()
        fruits: list[FruitNode] = (
            strawchemy.field(order_by_input=declared)
            if field_kwarg == "order_by_input"
            else strawchemy.field(distinct_on=declared)
        )

    return str(strawberry.Schema(query=Query))


def _member_names(graphql_type: GraphQLNamedType | None) -> set[str]:
    if isinstance(graphql_type, GraphQLEnumType):
        return set(graphql_type.values)
    assert isinstance(graphql_type, GraphQLInputObjectType)
    return set(graphql_type.fields)


@pytest.mark.parametrize(
    ("decorator", "name", "argument", "field_kwarg", "generated_fields"),
    [
        pytest.param(
            "order",
            "FruitOrderBy",
            "orderBy",
            "order_by_input",
            {"id", "name", "sweetness", "colorId", "color"},
            id="order",
        ),
        pytest.param(
            "distinct_on",
            "FruitDistinctOnFields",
            "distinctOn",
            "distinct_on",
            {"id", "name", "sweetness", "colorId"},
            id="distinct-on",
        ),
    ],
)
@pytest.mark.parametrize("declared_first", [True, False])
def test_declaration_keeps_its_name_over_generated_type(
    decorator: str, name: str, argument: str, field_kwarg: str, generated_fields: set[str], declared_first: bool
) -> None:
    """Test that a declaration owns its name, the relation argument generated for its model taking another, in either order."""
    sdl = _declaration_and_relation_argument_schema(decorator, name, field_kwarg, declared_first=declared_first)
    schema = build_schema(sdl)
    color_type = schema.get_type("ColorType")
    assert isinstance(color_type, GraphQLObjectType)
    generated = get_named_type(color_type.fields["fruits"].args[argument].type)

    assert _member_names(schema.get_type(name)) == {"name"}
    assert generated.name != name
    assert _member_names(generated) == generated_fields


@pytest.mark.parametrize(
    ("decorator", "name", "argument", "field_kwarg", "declared_first", "generated_name"),
    [
        pytest.param("order", "FruitOrderBy", "orderBy", "order_by_input", True, "FruitOrderBy1", id="order-declared"),
        pytest.param(
            "order",
            "FruitOrderBy",
            "orderBy",
            "order_by_input",
            False,
            "ColorOrderByFruitOrderBy",
            id="order-generated",
        ),
        pytest.param(
            "distinct_on",
            "FruitDistinctOnFields",
            "distinctOn",
            "distinct_on",
            True,
            "FruitDistinctOnFields1",
            id="distinct-on-declared",
        ),
        pytest.param(
            "distinct_on",
            "FruitDistinctOnFields",
            "distinctOn",
            "distinct_on",
            False,
            "FruitDistinctOnFields1",
            id="distinct-on-generated",
        ),
    ],
)
def test_generated_type_name_displaced_by_declaration(
    decorator: str, name: str, argument: str, field_kwarg: str, declared_first: bool, generated_name: str
) -> None:
    """Test that a generated type displaced by a declaration takes a name set by the declaration order alone.

    A root-level generated type takes the next free numbered name; one first registered within a parent input
    keeps that input's path name, so the name depends on whether the declaration comes first.
    """
    sdls = [
        _declaration_and_relation_argument_schema(decorator, name, field_kwarg, declared_first=declared_first)
        for _ in range(2)
    ]
    color_type = build_schema(sdls[0]).get_type("ColorType")
    assert isinstance(color_type, GraphQLObjectType)

    assert get_named_type(color_type.fields["fruits"].args[argument].type).name == generated_name
    assert sdls[0] == sdls[1]


@pytest.mark.parametrize("declared_first", [True, False])
@pytest.mark.parametrize(
    ("kwargs", "relation_input", "relation_fields"),
    [
        pytest.param({}, "FruitCreateFruitColorInput", {"id", "name"}, id="declared"),
        pytest.param({"scope": "schema"}, "FruitColorInput", {"name"}, id="scope-schema"),
    ],
)
def test_nested_generated_input_displaced_by_declaration(
    kwargs: dict[str, Any], relation_input: str, relation_fields: set[str], declared_first: bool
) -> None:
    """Test that a nested input generated under a declared name takes its path name, unless the declaration stands in."""
    strawchemy = Strawchemy("postgresql")

    def declare() -> type[Any]:
        return strawchemy.create_input(Color, include=["name"], **kwargs)(type("FruitColorInput", (), {}))

    declared = declare() if declared_first else None

    @strawchemy.create_input(Fruit, include="all")
    class FruitCreate: ...

    if declared is None:
        declared = declare()

    @strawchemy.type(Fruit, include="all")
    class FruitNode: ...

    @strawchemy.type(Color, include="all")
    class ColorNode: ...

    @strawberry.type
    class Mutation:
        create_fruit: FruitNode = strawchemy.create(FruitCreate)
        create_color: ColorNode = strawchemy.create(declared)

    schema = build_schema(str(strawberry.Schema(query=DefaultQuery, mutation=Mutation)))
    fruit_create = schema.get_type("FruitCreate")
    assert isinstance(fruit_create, GraphQLInputObjectType)
    color_relation = get_named_type(fruit_create.fields["color"].type)
    assert isinstance(color_relation, GraphQLInputObjectType)
    nested = get_named_type(color_relation.fields["create"].type)

    assert _member_names(schema.get_type("FruitColorInput")) == {"name"}
    assert nested.name == relation_input
    assert _member_names(nested) == relation_fields


@pytest.mark.parametrize("declared_first", [True, False])
def test_nested_generated_input_displaced_onto_a_declared_path_name(declared_first: bool) -> None:
    """Test that a nested input displaced by a declaration skips its path name when another declaration holds it."""
    strawchemy = Strawchemy("postgresql")

    @strawchemy.create_input(Color, include=["name"])
    class FruitCreateFruitColorInput: ...

    def declare() -> type[Any]:
        return strawchemy.create_input(Color, include=["name"])(type("FruitColorInput", (), {}))

    declared = declare() if declared_first else None

    @strawchemy.create_input(Fruit, include="all")
    class FruitCreate: ...

    if declared is None:
        declared = declare()

    @strawchemy.type(Fruit, include="all")
    class FruitNode: ...

    @strawchemy.type(Color, include="all")
    class ColorNode: ...

    @strawberry.type
    class Mutation:
        create_fruit: FruitNode = strawchemy.create(FruitCreate)
        create_color: ColorNode = strawchemy.create(declared)
        create_path_color: ColorNode = strawchemy.create(FruitCreateFruitColorInput)

    schema = build_schema(str(strawberry.Schema(query=DefaultQuery, mutation=Mutation)))
    fruit_create = schema.get_type("FruitCreate")
    assert isinstance(fruit_create, GraphQLInputObjectType)
    color_relation = get_named_type(fruit_create.fields["color"].type)
    assert isinstance(color_relation, GraphQLInputObjectType)
    nested = get_named_type(color_relation.fields["create"].type)

    assert _member_names(schema.get_type("FruitColorInput")) == {"name"}
    assert _member_names(schema.get_type("FruitCreateFruitColorInput")) == {"name"}
    assert nested.name not in {"FruitColorInput", "FruitCreateFruitColorInput"}
    assert _member_names(nested) == {"id", "name"}


def test_generated_enum_displaced_twice_keeps_following_its_name() -> None:
    """Test that a generated enum displaced onto a numbered name a later declaration claims is reused under its new name."""
    strawchemy = Strawchemy(StrawchemyConfig("postgresql", distinct_on="all"))

    @strawchemy.distinct_on(Fruit, include=["id"])
    class FruitDistinctOnFields: ...

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawchemy.distinct_on(Fruit, include=["name"])
    class FruitDistinctOnFields1: ...

    @strawchemy.type(Fruit, include="all")
    class FruitNode: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()
        fruits: list[FruitNode] = strawchemy.field()
        fruits_by_id: list[FruitNode] = strawchemy.field(distinct_on=FruitDistinctOnFields)
        fruits_by_name: list[FruitNode] = strawchemy.field(distinct_on=FruitDistinctOnFields1)

    schema = build_schema(str(strawberry.Schema(query=Query)))
    query = schema.query_type
    assert query is not None
    generated = get_named_type(query.fields["fruits"].args["distinctOn"].type)

    assert _member_names(schema.get_type("FruitDistinctOnFields1")) == {"name"}
    assert generated.name not in {"FruitDistinctOnFields", "FruitDistinctOnFields1"}
    assert _member_names(generated) == {"id", "name", "sweetness", "colorId"}


def test_declaration_named_like_a_builtin_type_error(strawchemy: Strawchemy) -> None:
    """Test that a declaration taking the name of a built-in strawchemy enum raises, naming the built-in by origin."""
    with pytest.raises(
        TypeNameConflictError,
        match=r"^Type `OrderByEnum` is already registered: `[\w.]+\.OrderByEnum` conflicts with `[\w.]+` \(model `User`\)$",
    ):

        @strawchemy.distinct_on(User, include=["name"])
        class OrderByEnum: ...


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("override_relation_filter", id="override_declared_after_auto_type"),
        pytest.param("override_relation_filter_paginated", id="override_declared_after_auto_type_paginated"),
        pytest.param("override_relation_filter_declared_first", id="override_declared_after_parent"),
    ],
)
def test_relation_to_overridden_type_has_its_filter(path: str) -> None:
    """Test that a relation retargeted to an override takes the filter argument the override declares."""
    query = import_module(f"tests.unit.schemas.override.{path}").Query
    schema = strawberry.Schema(query=query, scalar_overrides=SCALAR_OVERRIDES)

    assert re.search(r"colors\([^)]*filter: ColorFilter = null[^)]*\): \[ColorType!\]!", str(schema))


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("tests.unit.schemas.aggregations.type_mismatch", id="strawchemy_type"),
        pytest.param("tests.unit.schemas.aggregations.type_mismatch_plain_type", id="plain_type"),
        pytest.param("tests.unit.schemas.aggregations.type_mismatch_custom_resolver", id="custom_resolver"),
    ],
)
def test_aggregation_type_mismatch(module: str) -> None:
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape(
            """The `color_aggregations` field is defined with `root_aggregations` enabled but the field type is not a root aggregation type."""
        ),
    ):
        import_module(module)


@pytest.mark.parametrize(
    ("module", "type_name"),
    [
        pytest.param("root_list", "Plain", id="root_list"),
        pytest.param("root_single", "Plain", id="root_single"),
        pytest.param("root_scalar", "int", id="root_scalar"),
        pytest.param("root_union_plain_first", "Plain", id="root_union_plain_first"),
        pytest.param("type_body_field", "Plain", id="type_body_field"),
        pytest.param("default_order_by_no_resolver", "Plain", id="default_order_by_no_resolver"),
        pytest.param("create_mutation", "Plain", id="create_mutation"),
        pytest.param("upsert_mutation", "Plain", id="upsert_mutation"),
        pytest.param("update_mutation", "Plain", id="update_mutation"),
        pytest.param("delete_mutation", "Plain", id="delete_mutation"),
    ],
)
def test_resolverless_field_on_plain_type_fail(module: str, type_name: str) -> None:
    """Test that a root field without resolver is rejected when its type is not a strawchemy type."""
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape(f"The `plain` field has no resolver but its type `{type_name}` is not a strawchemy type."),
    ):
        import_module(f"tests.unit.schemas.plain_type.{module}")


def test_default_order_by_on_plain_type_fail() -> None:
    """Test that `default_order_by` is rejected on a field with a resolver returning a plain type."""
    with pytest.raises(
        StrawchemyFieldError,
        match=re.escape(
            "`default_order_by` cannot be set on `plain` because its type `Plain` is not a strawchemy type."
        ),
    ):
        import_module("tests.unit.schemas.plain_type.default_order_by_resolver")


@pytest.mark.parametrize("module", ["delete_mutation", "update_mutation"])
def test_mutation_type_resolved_after_definition(module: str) -> None:
    """Test that a list mutation type defined after the field is validated once resolved."""
    schema_module = import_module(f"tests.unit.schemas.unresolved_type.{module}")
    strawberry.Schema(query=schema_module.Query, mutation=schema_module.Mutation)


@pytest.mark.parametrize(
    ("module", "message"),
    [
        pytest.param("delete_mutation_not_list", "Type of delete mutation must be a list: delete_color", id="delete"),
        pytest.param(
            "update_mutation_not_list", "Type of update mutation by filter must be a list: update_color", id="update"
        ),
    ],
)
def test_mutation_type_resolved_after_definition_not_list_fail(module: str, message: str) -> None:
    """Test that a non-list mutation type defined after the field fails the list check once resolved."""
    schema_module = import_module(f"tests.unit.schemas.unresolved_type.{module}")
    # Strawberry wraps errors raised while resolving field types at schema build.
    with pytest.raises(TypeError, match=re.escape(message)) as exc_info:
        strawberry.Schema(query=schema_module.Query, mutation=schema_module.Mutation)
    assert isinstance(exc_info.value.__cause__, StrawchemyFieldError)


@pytest.mark.parametrize(
    ("module", "context"),
    [
        pytest.param("root_list", "The `errors` field has no resolver but", id="root_list"),
        pytest.param("create_mutation", "The `errors` field has no resolver but", id="create_mutation"),
        pytest.param(
            "default_order_by_resolver",
            "`default_order_by` cannot be set on `errors` because",
            id="default_order_by_resolver",
        ),
    ],
)
def test_error_only_type_fail(module: str, context: str) -> None:
    """Test that a field needing a strawchemy type is rejected when its type only contains error types."""
    with pytest.raises(StrawchemyFieldError, match=re.escape(f"{context} its type only contains error types.")):
        import_module(f"tests.unit.schemas.error_only_type.{module}")


def test_error_only_type_with_resolver_accepted() -> None:
    """Test that a field with a resolver can return only error types."""
    from tests.unit.schemas.error_only_type.resolver import Query

    assert "errors: [ValidationErrorType!]!" in str(strawberry.Schema(query=Query))


@pytest.mark.snapshot
def test_plain_type_fields_accepted(graphql_snapshot: SnapshotAssertion) -> None:
    """Test that plain types are accepted behind a resolver or after the strawchemy type of a union."""
    from tests.unit.schemas.plain_type.accepted import Mutation, Query

    schema = strawberry.Schema(query=Query, mutation=Mutation)
    assert textwrap.dedent(str(schema)).strip() == graphql_snapshot


def test_registry_type_shadows_module_name() -> None:
    """Test that a postponed annotation resolves a registry type over a module name bound to another type."""
    from tests.unit.schemas.plain_type.registry_shadowing import Query, RegistryColorType

    field = get_object_definition(Query, strict=True).get_field("color")
    assert field is not None
    assert field.type is RegistryColorType


def test_postponed_field_resolves_type_defined_after_it() -> None:
    """Test that a postponed field annotation resolves a registry type defined later over a module name."""
    from tests.unit.schemas.late_type.root_field import Query, RegistryColorType

    strawberry.Schema(query=Query)
    field = get_object_definition(Query, strict=True).get_field("colors")
    assert field is not None
    assert strawberry_contained_user_type(field.type) is RegistryColorType


def test_postponed_delete_mutation_resolves_type_defined_after_it() -> None:
    """Test that a postponed delete mutation annotation resolves a strawchemy type defined later in the module."""
    from tests.unit.schemas.late_type.delete_mutation import ColorType, Mutation

    strawberry.Schema(query=DefaultQuery, mutation=Mutation)
    field = get_object_definition(Mutation, strict=True).get_field("delete_colors")
    assert field is not None
    assert strawberry_contained_user_type(field.type) is ColorType


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("late_type.relation_annotation", id="same_module"),
        pytest.param("late_type.relation_annotation_private", id="with_private_field"),
        pytest.param("late_type.relation_annotation_class_alias", id="with_class_body_alias"),
        pytest.param("late_type_module.query", id="other_module"),
    ],
)
def test_postponed_relation_annotation_resolves_type_defined_after_it(module: str) -> None:
    """Test that a relation annotated with a later-defined type keeps the other base annotations resolvable."""
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


@pytest.mark.parametrize("field_name", ["extra", "extras"])
def test_postponed_type_field_resolves_plain_type_defined_after_it(field_name: str) -> None:
    """Test that a postponed annotation on a strawchemy type resolves a plain strawberry type defined later."""
    from tests.unit.schemas.late_type.plain_field import ColorType, Later, Query

    strawberry.Schema(query=Query)
    field = get_object_definition(ColorType, strict=True).get_field(field_name)
    assert field is not None
    assert strawberry_contained_user_type(field.type) is Later


def test_postponed_type_keeps_generated_relation_types() -> None:
    """Test that a strawchemy type annotating a later plain type still resolves its generated relation types."""
    from tests.unit.schemas.late_type.plain_field import ColorType, Query

    strawberry.Schema(query=Query)
    field = get_object_definition(ColorType, strict=True).get_field("fruits")
    assert field is not None
    assert strawberry_contained_user_type(field.type).__dto_model__ is Fruit


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
        pytest.param("model_field.field_options.Query", id="model_field_options"),
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
        pytest.param("filters.field_filter_object_relation.Query", id="field_filter_object_relation"),
        pytest.param("order.type_order_by.Query", id="type_order_by"),
        pytest.param("order.field_order_by.Query", id="field_order_by"),
        pytest.param("order.field_order_by_all.Query", id="field_order_by_all"),
        pytest.param("order.field_order_by_all_object_relation.Query", id="field_order_by_all_object_relation"),
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
        pytest.param("interface.implements_interface.Query", id="implements_interface"),
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
@pytest.mark.extras
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
        pytest.param("sql_expression_default.Mutation", id="sql_expression_default"),
        pytest.param("create_explicit_include.Mutation", id="create_explicit_include"),
        pytest.param("table_mapped.Mutation", id="table_mapped"),
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


@pytest.mark.parametrize(
    ("path", "field_name", "description"),
    [
        pytest.param("create.Mutation", "create_group", "Create object in the GroupType collection", id="create"),
        pytest.param(
            "create.Mutation", "create_groups", "Create objects in the GroupType collection", id="create_list"
        ),
        pytest.param("update.Mutation", "update_group_by_id", "Update object in the GroupType collection", id="update"),
        pytest.param(
            "update.Mutation", "update_groups", "Update objects in the GroupType collection", id="update_filter"
        ),
        pytest.param("upsert.Mutation", "upsert_fruit", "Upsert object in the FruitType collection", id="upsert"),
        pytest.param(
            "delete.Mutation", "delete_groups", "Delete objects in the GroupType collection", id="delete_list"
        ),
    ],
)
def test_mutation_field_description(path: str, field_name: str, description: str) -> None:
    """Test that generated mutation fields describe the mutation instead of a fetch."""
    module, mutation_name = f"tests.unit.schemas.mutations.{path}".rsplit(".", maxsplit=1)
    mutation_class = getattr(import_module(module), mutation_name)
    strawberry.Schema(query=DefaultQuery, mutation=mutation_class, scalar_overrides=SCALAR_OVERRIDES)

    field = get_object_definition(mutation_class, strict=True).get_field(field_name)
    assert field is not None
    assert field.description == description


@pytest.mark.parametrize(
    ("type_name", "field_name", "description"),
    [
        pytest.param("Query", "plain", None, id="plain_list_resolver"),
        pytest.param("Query", "plain_by_id", None, id="plain_resolver"),
        pytest.param("ColorType", "plain", None, id="plain_type_body_resolver"),
        pytest.param("Mutation", "create_plain", None, id="plain_create_resolver"),
        pytest.param("Mutation", "create_color", "Create object in the ColorType collection", id="error_union"),
        pytest.param("Query", "colors", "Fetch objects from the ColorType collection", id="strawchemy_list"),
        pytest.param(
            "Query", "color_or_plain", "Fetch object from the ColorType collection by id", id="strawchemy_first_union"
        ),
    ],
)
def test_plain_type_field_description(type_name: str, field_name: str, description: str | None) -> None:
    """Test that fields only get an auto description when they return a strawchemy type."""
    module = import_module("tests.unit.schemas.plain_type.accepted")
    strawberry.Schema(query=module.Query, mutation=module.Mutation)

    field = get_object_definition(getattr(module, type_name), strict=True).get_field(field_name)
    assert field is not None
    assert field.description == description


def test_mutation_field_explicit_description(strawchemy: Strawchemy) -> None:
    """Test that an explicit description wins over the generated mutation description."""

    @strawchemy.type(Color, include=["name"])
    class ColorType: ...

    @strawchemy.create_input(Color, include=["name"])
    class ColorCreate: ...

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreate, description="custom")

    strawberry.Schema(query=DefaultQuery, mutation=Mutation)
    field = get_object_definition(Mutation, strict=True).get_field("create_color")
    assert field is not None
    assert field.description == "custom"


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
def test_pydantic_postponed_field_resolves_model_defined_after_it() -> None:
    """Test that a postponed annotation on a strawchemy pydantic model resolves a model defined later."""
    # Not importing the names: pydantic would otherwise resolve them from this frame.
    module = import_module("tests.unit.schemas.pydantic.late_type")

    assert module.ColorCreate.model_validate({"name": "red", "extra": {"x": 1}}).model_dump()["extra"] == {"x": 1}


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


def _tag_validation_body() -> dict[str, Any]:
    from pydantic import field_validator, model_validator

    class Body:
        name: str

        @field_validator("name")
        @classmethod
        def lower_case(cls, value: str) -> str:
            if not value.islower():
                msg = "name must be lower cased"
                raise ValueError(msg)
            return value

        @model_validator(mode="after")
        def not_reserved(self) -> Body:
            if self.name == "admin":
                msg = "reserved name"
                raise ValueError(msg)
            return self

        def shout(self) -> str:
            return self.name.upper()

        @property
        def shout_property(self) -> str:
            return self.shout()

        @classmethod
        def label(cls) -> str:
            return cls.__name__

    return {key: value for key, value in vars(Body).items() if not key.startswith("__")}


@pytest.mark.parametrize("mode", ["create", "pk_update", "filter_update"])
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_validation_keeps_class_body(mode: str, strawchemy: Strawchemy) -> None:
    """Test that validators and methods declared in a pydantic validation class body are kept."""
    from pydantic import ValidationError

    from tests.unit.models import Tag

    decorator = getattr(strawchemy.pydantic, mode)(Tag, include=["name"])
    validation = decorator(type("TagValidation", (), _tag_validation_body()))
    pk = {"id": "da636751-b276-4546-857f-3c73ea914467"} if mode == "pk_update" else {}

    for name in ("UPPER", "admin"):
        with pytest.raises(ValidationError):
            validation(name=name, **pk)

    instance = validation(name="bob", **pk)
    assert instance.shout() == "BOB"
    assert instance.shout_property == "BOB"
    assert validation.label() == "TagValidation"


@pytest.mark.filterwarnings("error")
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_validation_class_body_validators_with_annotated_field(strawchemy: Strawchemy) -> None:
    """Test that class-body validators run, without warnings, on a field the class body re-annotates with a default."""
    from pydantic import ValidationError, field_validator, model_validator

    from tests.unit.models import Tag

    @strawchemy.pydantic.create(Tag, include=["name"])
    class TagValidation:
        name: str | None = None

        @field_validator("name")
        @classmethod
        def lower_case(cls, value: str | None) -> str | None:
            if value is not None and not value.islower():
                msg = "name must be lower cased"
                raise ValueError(msg)
            return value

        @model_validator(mode="after")
        def not_reserved(self) -> Self:
            if self.name == "admin":
                msg = "reserved name"
                raise ValueError(msg)
            return self

    validation: type[Any] = TagValidation
    field = validation.model_fields["name"]
    assert field.annotation == str | None
    assert field.default is None
    assert validation().name is None
    assert validation(name="bob").name == "bob"
    for name in ("UPPER", "admin"):
        with pytest.raises(ValidationError):
            validation(name=name)


@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_validation_keeps_user_bases(strawchemy: Strawchemy) -> None:
    """Test that a pydantic validation class keeps the validators and methods of its plain bases."""
    from pydantic import ValidationError

    from tests.unit.models import Tag

    mixin = type("TagValidationMixin", (), _tag_validation_body())
    validation: type[Any] = strawchemy.pydantic.create(Tag, include=["name"])(type("TagValidation", (mixin,), {}))

    with pytest.raises(ValidationError):
        validation(name="UPPER")
    assert validation(name="bob").shout() == "BOB"
    assert issubclass(validation, mixin)


@pytest.mark.parametrize(
    ("name", "expected_error"),
    [
        pytest.param(
            "UPPER",
            {"id": "ERROR", "loc": ["name"], "message": "Value error, name must be lower cased", "type": "value_error"},
            id="field-validator",
        ),
        pytest.param(
            "admin",
            {"id": "ERROR", "loc": [], "message": "Value error, reserved name", "type": "value_error"},
            id="model-validator",
        ),
    ],
)
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_validation_class_body_in_mutation(
    name: str, expected_error: dict[str, Any], strawchemy: Strawchemy
) -> None:
    """Test that a mutation rejects input failing validators declared in the validation class body."""
    from strawchemy import ValidationErrorType
    from strawchemy.validation.pydantic import PydanticValidation
    from tests.unit.models import Tag

    @strawchemy.create_input(Tag, include=["name"])
    class TagCreate: ...

    @strawchemy.type(Tag, include=["id", "name"])
    class TagType: ...

    validation = strawchemy.pydantic.create(Tag, include=["name"])(type("TagValidation", (), _tag_validation_body()))

    @strawberry.type
    class Mutation:
        create_tag: TagType | ValidationErrorType = strawchemy.create(
            TagCreate, validation=PydanticValidation(validation)
        )

    query = f"""
        mutation {{
            createTag(data: {{ name: "{name}" }}) {{
                __typename
                ... on ValidationErrorType {{
                    id
                    errors {{ id loc message type }}
                }}
            }}
        }}
    """
    schema = strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES)
    result = schema.execute_sync(query, context_value=MockContext("postgresql"))
    assert not result.errors
    assert result.data
    assert result.data["createTag"]["__typename"] == "ValidationErrorType"
    assert result.data["createTag"]["errors"] == [expected_error]


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


@pytest.mark.parametrize("container_scope", [pytest.param(None, id="unscoped"), pytest.param("schema", id="scoped")])
def test_scoped_type_shares_relation_aggregate(strawchemy: Strawchemy, container_scope: TypeScope | None) -> None:
    """Test that a later type aggregating the same relation as a schema-scoped type reuses its aggregate type (#419)."""

    @strawchemy.type(Color, include="all", scope="schema")
    class ColorType: ...

    @strawchemy.type(Container, include=["id", "fruits"], scope=container_scope)
    class ContainerType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()
        containers: list[ContainerType] = strawchemy.field()

    schema_str = str(strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES))

    assert schema_str.count("fruitsAggregate: FruitAggregate!") == 2
    assert schema_str.count("type FruitAggregate ") == 1


def test_scoped_input_shares_upsert_enums(strawchemy: Strawchemy) -> None:
    """Test that a later input upserting the same relation as a schema-scoped input reuses its upsert enums (#419)."""

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawchemy.create_input(Color, include="all", scope="schema")
    class ColorCreate: ...

    @strawchemy.pk_update_input(Color, include="all")
    class ColorUpdate: ...

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreate)
        update_colors: list[ColorType] = strawchemy.update_by_ids(ColorUpdate)

    schema_str = str(strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES))

    assert schema_str.count("enum ColorFruitsUpdateFields ") == 1
    assert schema_str.count("enum ColorFruitsConflictFields ") == 1


def test_scoped_aggregate_filter_shares_argument_enums(strawchemy: Strawchemy) -> None:
    """Test that a filter aggregating the same model as a schema-scoped aggregate filter reuses its argument enums (#419)."""

    @strawchemy.aggregate_filter(Fruit, include="all", scope="schema")
    class FruitAggregateFilter: ...

    @strawchemy.filter(Color, include="all")
    class ColorFilter: ...

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter)

    schema_str = str(strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES))

    assert schema_str.count("enum FruitCountFields ") == 1


@pytest.mark.parametrize("scope", [None, "schema"])
def test_schema_scope_does_not_leak_into_related_model_types(strawchemy: Strawchemy, scope: TypeScope | None) -> None:
    """Test that types of models related to a schema-scoped type keep their own include (#421)."""

    @strawchemy.type(Group, include="all", scope="schema")
    class GroupType:
        pass

    @strawchemy.type(User, include=["name"], scope=scope)
    class UserNameType:
        pass

    @strawchemy.type(Tag, include=["name"], scope=scope)
    class TagNameType:
        pass

    @strawberry.type
    class Query:
        groups: list[GroupType] = strawchemy.field()
        users: list[UserNameType] = strawchemy.field()
        tags: list[TagNameType] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)
    user_type = schema.get_type_by_name("UserNameType")
    tag_type = schema.get_type_by_name("TagNameType")

    assert isinstance(user_type, StrawberryObjectDefinition)
    assert isinstance(tag_type, StrawberryObjectDefinition)
    assert [field.name for field in user_type.fields] == ["name"]
    assert [field.name for field in tag_type.fields] == ["name"]


def test_schema_scope_does_not_replace_references_to_related_model_types(strawchemy: Strawchemy) -> None:
    """Test that a field typed with a declared type of a model related to a schema-scoped type keeps that type."""

    @strawchemy.type(Group, include="all", scope="schema")
    class GroupType:
        pass

    @strawchemy.type(User, include=["name"])
    class UserNameType:
        pass

    @strawchemy.type(Color, include=["name"])
    class ColorNode:
        @strawberry.field
        def owner(self) -> UserNameType:
            raise NotImplementedError

    @strawberry.type
    class Query:
        groups: list[GroupType] = strawchemy.field()
        colors: list[ColorNode] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)
    color_type = schema.get_type_by_name("ColorNode")

    assert isinstance(color_type, StrawberryObjectDefinition)
    assert _field_type(color_type, "owner") is UserNameType


def test_schema_scope_input_does_not_leak_into_related_model_inputs(strawchemy: Strawchemy) -> None:
    """Test that a nested input built under a schema-scoped input is not reused by other root inputs."""

    @strawchemy.create_input(Group, include="all", scope="schema")
    class GroupCreate:
        pass

    @strawchemy.create_input(Department, include="all")
    class DepartmentCreate:
        pass

    @strawchemy.type(Group, include="all")
    class GroupNode:
        pass

    @strawberry.type
    class Mutation:
        create_department: GroupNode = strawchemy.create(DepartmentCreate)

    schema = strawberry.Schema(query=DefaultQuery, mutation=Mutation, scalar_overrides=SCALAR_OVERRIDES)
    department_input = schema.get_type_by_name("DepartmentCreate")
    assert isinstance(department_input, StrawberryObjectDefinition)
    users_input = get_object_definition(_field_type(department_input, "users"), strict=True)
    user_input = get_object_definition(_field_type(users_input, "create"), strict=True)

    assert user_input.name == "DepartmentUserInput"
    assert user_input.get_field("group") is not None


def test_schema_scope_type_is_not_shared_with_include_all_root(strawchemy: Strawchemy) -> None:
    """Test that an include-all root declared after a narrower schema-scoped type of the same model gets all fields."""

    @strawchemy.type(Tag, include=[SCALARS], scope="schema")
    class TagType:
        pass

    @strawchemy.type(Tag, include="all")
    class TagAllType:
        pass

    assert "groups" not in DTOInspect(TagType).annotations()
    assert "groups" in DTOInspect(TagAllType).annotations()


def test_schema_scope_type_is_reused_by_relations(strawchemy: Strawchemy) -> None:
    """Test that a relation of a type declared after a schema-scoped type resolves to the scoped type."""

    @strawchemy.type(Tag, include=[SCALARS], scope="schema")
    class TagType:
        pass

    @strawchemy.type(User, include=["name", "tag"])
    class UserNameType:
        pass

    @strawchemy.type(Tag, include=["name"])
    class TagNameType:
        pass

    @strawberry.type
    class Query:
        users: list[UserNameType] = strawchemy.field()
        tags: list[TagNameType] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)
    user_type = schema.get_type_by_name("UserNameType")
    tag_type = schema.get_type_by_name("TagNameType")

    assert isinstance(user_type, StrawberryObjectDefinition)
    assert isinstance(tag_type, StrawberryObjectDefinition)
    assert _field_type(user_type, "tag") is TagType
    assert [field.name for field in tag_type.fields] == ["name"]


class _DeclarationKind(NamedTuple):
    decorator: str
    root: Callable[[Strawchemy], type[Any]]
    schema: Callable[[Strawchemy, type[Any]], strawberry.Schema]
    field: str
    argument: str | None = None
    inner_fields: tuple[str, ...] = ()


def _root_type(**kwargs: Any) -> Callable[[Strawchemy], type[Any]]:
    return lambda strawchemy: strawchemy.type(Color, include="all", **kwargs)(type("ColorRoot", (), {}))


def _root_input(decorator: str) -> Callable[[Strawchemy], type[Any]]:
    return lambda strawchemy: getattr(strawchemy, decorator)(Color, include="all")(type("ColorRoot", (), {}))


def _query_schema(strawchemy: Strawchemy, root: type[Any]) -> strawberry.Schema:
    query = strawberry.type(
        type("Query", (), {"__annotations__": {"colors": list[root]}, "colors": strawchemy.field()})  # ty: ignore[invalid-type-form]
    )
    return strawberry.Schema(query=query, scalar_overrides=SCALAR_OVERRIDES)


def _argument_schema(field_kwarg: str) -> Callable[[Strawchemy, type[Any]], strawberry.Schema]:
    def schema(strawchemy: Strawchemy, root: type[Any]) -> strawberry.Schema:
        color_type = strawchemy.type(Color, include=["name"])(type("ColorNode", (), {}))
        field = (
            strawchemy.field(filter_input=root)
            if field_kwarg == "filter_input"
            else strawchemy.field(order_by_input=root)
        )
        query = strawberry.type(
            type("Query", (), {"__annotations__": {"colors": list[color_type]}, "colors": field})  # ty: ignore[invalid-type-form]
        )
        return strawberry.Schema(query=query, scalar_overrides=SCALAR_OVERRIDES)

    return schema


def _mutation_schema(strawchemy: Strawchemy, root: type[Any]) -> strawberry.Schema:
    color_type = strawchemy.type(Color, include=["name"])(type("ColorNode", (), {}))
    mutation = strawberry.type(
        type("Mutation", (), {"__annotations__": {"create_color": color_type}, "create_color": strawchemy.create(root)})
    )
    return strawberry.Schema(query=DefaultQuery, mutation=mutation, scalar_overrides=SCALAR_OVERRIDES)


_DECLARATION_KINDS = {
    "type": _DeclarationKind("type", _root_type(), _query_schema, "fruits"),
    "filter": _DeclarationKind("filter", _root_input("filter"), _argument_schema("filter_input"), "fruits"),
    "order": _DeclarationKind("order", _root_input("order"), _argument_schema("order_by_input"), "fruits"),
    "aggregate-filter": _DeclarationKind(
        "aggregate_filter", _root_input("filter"), _argument_schema("filter_input"), "fruitsAggregate"
    ),
    "create-input": _DeclarationKind(
        "create_input", _root_input("create_input"), _mutation_schema, "fruits", inner_fields=("create",)
    ),
    "upsert-update-fields": _DeclarationKind(
        "upsert_update_fields",
        _root_input("create_input"),
        _mutation_schema,
        "fruits",
        inner_fields=("upsert", "updateFields"),
    ),
    "order-argument": _DeclarationKind("order", _root_type(order="all"), _query_schema, "fruits", argument="orderBy"),
    "distinct-on-argument": _DeclarationKind(
        "distinct_on", _root_type(distinct_on="all"), _query_schema, "fruits", argument="distinctOn"
    ),
}


def _relation_type_name(schema: strawberry.Schema, kind: _DeclarationKind, type_name: str = "ColorRoot") -> str:
    graphql_schema = build_schema(str(schema))
    parent = graphql_schema.get_type(type_name)
    assert isinstance(parent, (GraphQLObjectType, GraphQLInputObjectType))
    field = parent.fields[kind.field]
    named = get_named_type(field.args[kind.argument].type if kind.argument else field.type)
    for inner_field in kind.inner_fields:
        assert isinstance(named, GraphQLInputObjectType)
        named = get_named_type(named.fields[inner_field].type)
    return named.name


@pytest.mark.parametrize("declared_first", [True, False])
@pytest.mark.parametrize("kind", _DECLARATION_KINDS.values(), ids=_DECLARATION_KINDS.keys())
def test_schema_scope_substitutes_generated_type(kind: _DeclarationKind, declared_first: bool) -> None:
    """Test that a schema-scoped declaration replaces the type generated for its model and kind, in either order."""
    strawchemy = Strawchemy("postgresql")

    def declare() -> type[Any]:
        return getattr(strawchemy, kind.decorator)(Fruit, include=["name"], scope="schema")(type("FruitScoped", (), {}))

    scoped = declare() if declared_first else None
    root = kind.root(strawchemy)
    if scoped is None:
        scoped = declare()

    assert _relation_type_name(kind.schema(strawchemy, root), kind) == "FruitScoped"


def _root_argument_type_name(
    strawchemy: Strawchemy, fruit_type: type[Any], field_kwargs: dict[str, Any], argument: str
) -> str:
    query = strawberry.type(
        type("Query", (), {"__annotations__": {"fruits": list[fruit_type]}, "fruits": strawchemy.field(**field_kwargs)})  # ty: ignore[invalid-type-form]
    )
    query_type = build_schema(str(strawberry.Schema(query=query, scalar_overrides=SCALAR_OVERRIDES))).query_type
    assert query_type is not None
    return get_named_type(query_type.fields["fruits"].args[argument].type).name


@pytest.mark.parametrize("declared_first", [True, False])
@pytest.mark.parametrize(
    ("decorator", "argument", "config", "type_kwargs", "field_kwargs"),
    [
        pytest.param("order", "orderBy", {}, {}, {"order_by_input": "all"}, id="field-order-by"),
        pytest.param("filter", "filter", {}, {}, {"filter_input": True}, id="field-filter"),
        pytest.param("distinct_on", "distinctOn", {}, {}, {"distinct_on": "all"}, id="field-distinct-on"),
        pytest.param("order", "orderBy", {"order_by": "all"}, {}, {}, id="config-order-by"),
        pytest.param("distinct_on", "distinctOn", {"distinct_on": "all"}, {}, {}, id="config-distinct-on"),
        pytest.param("order", "orderBy", {}, {"order": "all"}, {}, id="type-order-by"),
        pytest.param("distinct_on", "distinctOn", {}, {"distinct_on": "all"}, {}, id="type-distinct-on"),
    ],
)
def test_schema_scope_substitutes_generated_root_argument(
    decorator: str,
    argument: str,
    config: dict[str, Any],
    type_kwargs: dict[str, Any],
    field_kwargs: dict[str, Any],
    declared_first: bool,
) -> None:
    """Test that a schema-scoped declaration replaces the argument type generated for a root field, in either order."""
    strawchemy = Strawchemy(StrawchemyConfig("postgresql", **config))

    def declare() -> type[Any]:
        return getattr(strawchemy, decorator)(Fruit, include=["name"], scope="schema")(type("FruitScoped", (), {}))

    scoped = declare() if declared_first else None
    fruit_type = strawchemy.type(Fruit, include="all", **type_kwargs)(type("FruitNode", (), {}))
    if scoped is None:
        declare()

    assert _root_argument_type_name(strawchemy, fruit_type, field_kwargs, argument) == "FruitScoped"


@pytest.mark.parametrize(
    ("decorator", "argument", "kwarg", "on_type"),
    [
        pytest.param("order", "orderBy", "order_by_input", False, id="field-order-by"),
        pytest.param("filter", "filter", "filter_input", False, id="field-filter"),
        pytest.param("distinct_on", "distinctOn", "distinct_on", False, id="field-distinct-on"),
        pytest.param("order", "orderBy", "order", True, id="type-order-by"),
        pytest.param("distinct_on", "distinctOn", "distinct_on", True, id="type-distinct-on"),
    ],
)
def test_schema_scope_keeps_explicit_root_argument(decorator: str, argument: str, kwarg: str, on_type: bool) -> None:
    """Test that a root field argument given a declaration explicitly keeps it over a schema-scoped declaration."""
    strawchemy = Strawchemy("postgresql")
    getattr(strawchemy, decorator)(Fruit, include=["name"], scope="schema")(type("FruitScoped", (), {}))
    explicit = {kwarg: getattr(strawchemy, decorator)(Fruit, include=["id"])(type("FruitExplicit", (), {}))}
    fruit_type = strawchemy.type(Fruit, include="all", **(explicit if on_type else {}))(type("FruitNode", (), {}))

    assert _root_argument_type_name(strawchemy, fruit_type, {} if on_type else explicit, argument) == "FruitExplicit"


@pytest.mark.parametrize("declared_first", [True, False])
@pytest.mark.parametrize("forward_ref", [False, True])
def test_schema_scope_keeps_explicit_declared_type(declared_first: bool, forward_ref: bool) -> None:
    """Test that a field annotated with a declaration keeps it over a schema-scoped declaration, in either order."""
    strawchemy = Strawchemy("postgresql")

    def declare_scoped() -> None:
        strawchemy.type(Fruit, include=["name"], scope="schema")(type("FruitScoped", (), {}))

    if declared_first:
        declare_scoped()
    explicit = strawchemy.type(Fruit, include=["id"])(type("FruitType", (), {}))
    if not declared_first:
        declare_scoped()
    annotation = "list[FruitType]" if forward_ref else list[explicit]  # ty: ignore[invalid-type-form]
    color_type = strawchemy.type(Color, include="all")(
        type("ColorType", (), {"__annotations__": {"fruits": annotation}})
    )
    query = strawberry.type(
        type("Query", (), {"__annotations__": {"colors": list[color_type]}, "colors": strawchemy.field()})  # ty: ignore[invalid-type-form]
    )

    schema = build_schema(str(strawberry.Schema(query=query, scalar_overrides=SCALAR_OVERRIDES)))
    color = schema.get_type("ColorType")
    assert isinstance(color, GraphQLObjectType)
    assert get_named_type(color.fields["fruits"].type).name == "FruitType"


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        pytest.param(_DECLARATION_KINDS["type"], "FruitType", id="type"),
        pytest.param(_DECLARATION_KINDS["filter"], "FruitBoolExp", id="filter"),
        pytest.param(_DECLARATION_KINDS["order"], "FruitOrderBy", id="order"),
        pytest.param(_DECLARATION_KINDS["order-argument"], "FruitOrderBy", id="order-argument"),
    ],
)
def test_schema_scope_declaration_takes_over_generated_name(kind: _DeclarationKind, name: str) -> None:
    """Test that a schema-scoped declaration named like a type already generated for it replaces that type."""
    strawchemy = Strawchemy("postgresql")
    root = kind.root(strawchemy)
    getattr(strawchemy, kind.decorator)(Fruit, include=["name"], scope="schema")(type(name, (), {}))

    schema = kind.schema(strawchemy, root)

    declared = build_schema(str(schema)).get_type(name)
    assert isinstance(declared, (GraphQLObjectType, GraphQLInputObjectType))

    assert _relation_type_name(schema, kind) == name
    assert "name" in declared.fields
    assert "sweetness" not in declared.fields


@pytest.mark.parametrize("declared_first", [True, False])
@pytest.mark.parametrize("kind", ["type", "filter", "order"])
def test_relation_back_reference_points_to_its_declaration(kind: str, declared_first: bool) -> None:
    """Test that a relation of a declaration leads back to it, an unscoped declaration of the related model standing apart."""
    declaration_kind = _DECLARATION_KINDS[kind]
    strawchemy = Strawchemy("postgresql")

    def declare() -> type[Any]:
        return getattr(strawchemy, declaration_kind.decorator)(Fruit, include="all")(type("FruitDeclared", (), {}))

    declared = declare() if declared_first else None
    root = declaration_kind.root(strawchemy)
    if declared is None:
        declared = declare()
    schema = declaration_kind.schema(strawchemy, root)
    graphql_schema = build_schema(str(schema))
    nested_name = _relation_type_name(schema, declaration_kind)
    nested = graphql_schema.get_type(nested_name)
    assert isinstance(nested, (GraphQLObjectType, GraphQLInputObjectType))

    assert nested_name != "FruitDeclared"
    assert get_named_type(nested.fields["color"].type).name == "ColorRoot"


@pytest.mark.parametrize("decorator", sorted({kind.decorator for kind in _DECLARATION_KINDS.values()}))
def test_second_schema_scoped_declaration_error(decorator: str) -> None:
    """Test that a schema-scoped declaration of a model and kind already scoped by another declaration raises."""
    strawchemy = Strawchemy("postgresql")
    getattr(strawchemy, decorator)(Fruit, include=["name"], scope="schema")(type("FruitScoped", (), {}))

    with pytest.raises(ScopeConflictError, match=r"^`[\w.]+` \(model `Fruit`\) cannot declare the schema scope"):
        getattr(strawchemy, decorator)(Fruit, include=["id"], scope="schema")(type("FruitOther", (), {}))


def test_schema_scoped_update_inputs_of_each_mode() -> None:
    """Test that a model takes a schema-scoped declaration for each update input mode without conflict."""
    strawchemy = Strawchemy("postgresql")
    by_pk = strawchemy.pk_update_input(Fruit, include=["name"], scope="schema")(type("FruitByPk", (), {}))
    by_filter = strawchemy.filter_update_input(Fruit, include=["name"], scope="schema")(type("FruitByFilter", (), {}))

    assert get_object_definition(by_pk, strict=True).name == "FruitByPk"
    assert get_object_definition(by_filter, strict=True).name == "FruitByFilter"


@pytest.mark.parametrize("decorator", ["type", "aggregate"])
def test_override_keyword_rejected(strawchemy: Strawchemy, decorator: str) -> None:
    """Test that passing override to a declaration decorator raises like any unexpected keyword."""
    with pytest.raises(TypeError, match="'override'"):
        getattr(strawchemy, decorator)(Fruit, include=["name"], override=True)(type("FruitDeclared", (), {}))


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


def _schema_field_type(schema: strawberry.Schema, type_name: str, field_name: str) -> object:
    type_definition = schema.get_type_by_name(type_name)
    assert isinstance(type_definition, StrawberryObjectDefinition)
    field = type_definition.get_field(field_name)
    return None if field is None else field.type


def test_class_annotation_does_not_leak_into_related_types(strawchemy: Strawchemy) -> None:
    """Test that a class annotation overrides its own field but not the same-named field of related types (#422)."""

    @strawchemy.type(Fruit, include="all")
    class FruitType:
        id: strawberry.ID

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)

    assert _schema_field_type(schema, "FruitType", "id") is strawberry.ID
    assert _schema_field_type(schema, "ColorType", "id") is UUID


def test_relay_node_id_annotation_does_not_leak_into_related_types(strawchemy: Strawchemy) -> None:
    """Test that a private relay NodeID annotation leaves the same-named field of related types public (#422)."""

    @strawchemy.type(Fruit, include="all")
    class FruitType:
        name: relay.NodeID[str]

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)

    assert _schema_field_type(schema, "FruitType", "name") is None
    assert _schema_field_type(schema, "ColorType", "name") is str


def _sdl_type_fields(schema: strawberry.Schema, type_name: str) -> dict[str, str]:
    graphql_type = build_schema(str(schema)).get_type(type_name)
    assert isinstance(graphql_type, (GraphQLInputObjectType, GraphQLObjectType, GraphQLEnumType))
    if isinstance(graphql_type, GraphQLEnumType):
        return dict.fromkeys(graphql_type.values, "")
    return {name: str(get_named_type(field.type)) for name, field in graphql_type.fields.items()}


def _assert_fruit_aggregate_order_by(schema: strawberry.Schema) -> None:
    assert _sdl_type_fields(schema, "FruitAggregateOrderBy") == {
        "avg": "FruitAggregateNumericFieldsOrderBy",
        "count": "OrderByEnum",
        "max": "FruitAggregateNumericFieldsOrderBy",
        "maxString": "FruitAggregateMinMaxStringFieldsOrderBy",
        "min": "FruitAggregateNumericFieldsOrderBy",
        "minString": "FruitAggregateMinMaxStringFieldsOrderBy",
        "stddevPop": "FruitAggregateNumericFieldsOrderBy",
        "stddevSamp": "FruitAggregateNumericFieldsOrderBy",
        "sum": "FruitAggregateNumericFieldsOrderBy",
        "varPop": "FruitAggregateNumericFieldsOrderBy",
        "varSamp": "FruitAggregateNumericFieldsOrderBy",
    }
    assert set(_sdl_type_fields(schema, "FruitAggregateNumericFieldsOrderBy")) == {"sweetness"}
    assert set(_sdl_type_fields(schema, "FruitAggregateMinMaxStringFieldsOrderBy")) == {"name"}


@pytest.mark.parametrize(
    "order",
    [
        pytest.param(["fruits"], id="relation_only"),
        pytest.param(["fruits", "name"], id="relation_and_string_column"),
        pytest.param(["fruits", "id"], id="relation_and_id"),
        pytest.param("all", id="all"),
    ],
)
def test_relation_aggregate_order_by_ignores_parent_order_list(strawchemy: Strawchemy, order: FieldSpec) -> None:
    """Test that a relation's aggregate order-by is built from the related model, whatever the parent orders by (#480)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        @strawchemy.type(Color, include="all", order=order)
        class ColorType: ...

        @strawberry.type
        class Query:
            colors: list[ColorType] = strawchemy.field()

        schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)

    _assert_fruit_aggregate_order_by(schema)


_PARENT_FIELD_SETTINGS = [
    pytest.param({"exclude": ["name"]}, id="exclude_shared_column"),
    pytest.param({"exclude": ["id", "name"]}, id="exclude_shared_columns"),
    pytest.param(
        {"include": "all", "aliases": {"name": "label"}},
        id="aliases",
        marks=pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    ),
    pytest.param({"include": "all", "type_map": {"name": int}}, id="type_map_by_name"),
]


@pytest.mark.parametrize("settings", _PARENT_FIELD_SETTINGS)
def test_relation_aggregate_order_by_ignores_parent_field_settings(
    strawchemy: Strawchemy, settings: dict[str, Any]
) -> None:
    """Test that a parent order-by's field-name-keyed settings do not apply to its relation aggregate (#480)."""

    @strawchemy.order(Color, **settings)
    class ColorOrderBy: ...

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field(order_by_input=ColorOrderBy)

    _assert_fruit_aggregate_order_by(strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES))


@pytest.mark.parametrize(
    "settings",
    [
        pytest.param({"include": ["fruits"]}, id="relation_only"),
        pytest.param({"include": ["fruits", "name"]}, id="relation_and_string_column"),
        pytest.param({"include": "all"}, id="all"),
        *_PARENT_FIELD_SETTINGS,
    ],
)
def test_relation_aggregate_filter_ignores_parent_field_settings(
    strawchemy: Strawchemy, settings: dict[str, Any]
) -> None:
    """Test that a relation's aggregate filter is built from the related model, whatever the parent's settings (#480)."""

    @strawchemy.filter(Color, **settings)
    class ColorFilter: ...

    @strawchemy.type(Color, include="all", filter_input=ColorFilter)
    class ColorType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)

    assert set(_sdl_type_fields(schema, "FruitAggregateBoolExp")) == {
        "avg",
        "count",
        "max",
        "maxString",
        "min",
        "minString",
        "stddevPop",
        "stddevSamp",
        "sum",
        "varPop",
        "varSamp",
    }
    assert set(_sdl_type_fields(schema, "FruitCountFields")) == {"id", "name", "colorId", "sweetness"}
    assert set(_sdl_type_fields(schema, "FruitMinMaxStringFieldsEnum")) == {"name"}


@pytest.fixture
def container_aggregates_schema(strawchemy: Strawchemy) -> strawberry.Schema:
    @strawchemy.filter(Container, include="all")
    class ContainerFilter: ...

    @strawchemy.order(Container, include="all")
    class ContainerOrderBy: ...

    @strawchemy.type(Container, include="all")
    class ContainerType: ...

    @strawberry.type
    class Query:
        containers: list[ContainerType] = strawchemy.field(
            filter_input=ContainerFilter, order_by_input=ContainerOrderBy
        )

    return strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)


@pytest.mark.parametrize("model", ["Fruit", "Vegetable"])
def test_aggregate_order_by_functions_match_aggregate_filter_arguments(
    container_aggregates_schema: strawberry.Schema, model: str
) -> None:
    """Test that each aggregate order-by function orders by the columns its aggregate filter accepts (#483)."""
    schema = build_schema(str(container_aggregates_schema))
    order_by = schema.get_type(f"{model}AggregateOrderBy")
    bool_exp = schema.get_type(f"{model}AggregateBoolExp")
    assert isinstance(order_by, GraphQLInputObjectType)
    assert isinstance(bool_exp, GraphQLInputObjectType)

    def order_by_columns(field: GraphQLInputField) -> set[str]:
        field_type = get_named_type(field.type)
        assert isinstance(field_type, GraphQLInputObjectType)
        return set(field_type.fields)

    def filter_columns(field: GraphQLInputField) -> set[str]:
        function_type = get_named_type(field.type)
        assert isinstance(function_type, GraphQLInputObjectType)
        arguments_type = get_named_type(function_type.fields["arguments"].type)
        assert isinstance(arguments_type, GraphQLEnumType)
        return set(arguments_type.values)

    assert {name: order_by_columns(field) for name, field in order_by.fields.items() if name != "count"} == {
        name: filter_columns(field) for name, field in bool_exp.fields.items() if name != "count"
    }


def test_aggregate_numeric_order_by_holds_numeric_columns_only(container_aggregates_schema: strawberry.Schema) -> None:
    """Test that a model without numeric columns gets no numeric aggregate order-by type (#483)."""
    assert build_schema(str(container_aggregates_schema)).get_type("VegetableAggregateNumericFieldsOrderBy") is None


def _album_schema(strawchemy: Strawchemy) -> strawberry.Schema:
    @strawchemy.filter(Album, include="all")
    class AlbumFilter: ...

    @strawchemy.type(Album, include="all", order=["tracks"])
    class AlbumType: ...

    @strawberry.type
    class Query:
        albums: list[AlbumType] = strawchemy.field(filter_input=AlbumFilter)

    return strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)


def test_aggregate_order_by_sum_interval_holds_interval_columns(strawchemy: Strawchemy) -> None:
    """Test that sum and avg order by numeric columns while sumInterval orders by interval columns (#483, #486)."""
    schema = _album_schema(strawchemy)

    order_by = _sdl_type_fields(schema, "TrackAggregateOrderBy")
    assert (order_by["sum"], order_by["avg"], order_by["sumInterval"]) == (
        "TrackAggregateNumericFieldsOrderBy",
        "TrackAggregateNumericFieldsOrderBy",
        "TrackAggregateSumIntervalFieldsOrderBy",
    )
    assert set(_sdl_type_fields(schema, "TrackAggregateNumericFieldsOrderBy")) == {"rating"}
    assert set(_sdl_type_fields(schema, "TrackAggregateSumIntervalFieldsOrderBy")) == {"duration", "wrappedDuration"}
    assert _sdl_type_fields(schema, "TrackAggregateBoolExp")["sumInterval"] == "TrackAggregateBoolExpSumInterval"
    assert _sdl_type_fields(schema, "TrackAggregateBoolExpSumInterval")["predicate"] == "IntervalComparison"


@pytest.mark.parametrize(
    ("dialect", "sum_fields", "sums_intervals"),
    [
        pytest.param("postgresql", {"duration", "wrappedDuration", "rating"}, True, id="postgresql"),
        pytest.param("mysql", {"rating"}, False, id="mysql"),
        pytest.param("sqlite", {"rating"}, False, id="sqlite"),
    ],
)
def test_sum_over_interval_columns_follows_native_interval_support(
    dialect: SupportedDialect, sum_fields: set[str], sums_intervals: bool
) -> None:
    """Test that interval columns are summed only on dialects storing intervals natively (#486)."""
    schema = _album_schema(Strawchemy(dialect))

    assert set(_sdl_type_fields(schema, "TrackSumFields")) == sum_fields
    assert ("sumInterval" in _sdl_type_fields(schema, "TrackAggregateBoolExp")) is sums_intervals
    assert ("sumInterval" in _sdl_type_fields(schema, "TrackAggregateOrderBy")) is sums_intervals


def test_default_order_by_on_non_list_field_raises() -> None:
    with pytest.raises(StrawchemyFieldError, match="list field"):
        import_module("tests.unit.schemas.default_order_by_non_list")


def test_default_order_by_wrong_model_column_raises() -> None:
    with pytest.raises(StrawchemyFieldError, match="not a column"):
        import_module("tests.unit.schemas.default_order_by_invalid")


def test_validation_for_another_model_raises() -> None:
    """Test that a validation type mapping a different model than the input type raises."""
    with pytest.raises(StrawchemyFieldError, match="GroupCreateValidation validates Group, but UserCreate maps User"):
        import_module("tests.unit.schemas.pydantic.validation_model_mismatch")


def test_aggregation_order_by_aliased_column_no_key_error() -> None:
    """Schema build must not raise KeyError for aggregatable columns with a field-level alias.

    Regression test for the bug introduced by the "centralize field_map" refactor.
    `_order_by_aggregation_fields` was keying `model_fields` by `prop.key` (raw SQLAlchemy
    attribute name) but looking up by `name.field_definition.name` (alias-aware). For any
    aggregatable column with a Purpose.READ alias the subscript raised a KeyError.
    """
    from tests.unit.schemas.order.order_by_aliased_aggregation import Query

    # Schema build must not raise KeyError.
    schema = strawberry.Schema(query=Query, scalar_overrides=SCALAR_OVERRIDES)
    schema_sdl = str(schema)
    # The aggregate order-by input type for the aliased model must appear in the schema.
    assert "AliasedItemAggregateOrderBy" in schema_sdl


@pytest.mark.parametrize(
    "decorator",
    ["create_input", "pk_update_input", "filter_update_input", "upsert_update_fields", "upsert_conflict_fields"],
)
def test_write_input_on_join_mapped_model_fail(strawchemy: Strawchemy, decorator: str) -> None:
    """Test that a write input on a class mapped onto a join is rejected when decorated."""
    with pytest.raises(ReadOnlyModelError, match=JOIN_MAPPED_ERROR):

        @getattr(strawchemy, decorator)(JoinedAB, include="all")
        class JoinedABInput: ...


@pytest.mark.extras
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
@pytest.mark.parametrize("decorator", ["create", "pk_update", "filter_update"])
def test_pydantic_write_model_on_join_mapped_model_fail(strawchemy: Strawchemy, decorator: str) -> None:
    """Test that a pydantic validation model on a class mapped onto a join is rejected when decorated."""
    with pytest.raises(ReadOnlyModelError, match=JOIN_MAPPED_ERROR):

        @getattr(strawchemy.pydantic, decorator)(JoinedAB, include="all")
        class JoinedABValidation: ...


@pytest.mark.parametrize("decorator", ["create_input", "pk_update_input", "filter_update_input"])
@pytest.mark.parametrize(
    ("owner", "joined_name"),
    [
        pytest.param(JoinOwner, "JoinedAB", id="column_property"),
        pytest.param(ColumnJoinOwner, "ColumnJoinedAB", id="plain_columns"),
    ],
)
def test_write_input_with_relation_to_join_mapped_model_fail(
    strawchemy: Strawchemy, decorator: str, owner: type[Any], joined_name: str
) -> None:
    """Test that a write input including a relation to a class mapped onto a join is rejected when decorated."""
    with pytest.raises(ReadOnlyModelError, match=re.escape(JOIN_MAPPED_ERROR_TEMPLATE.format(joined_name))):

        @getattr(strawchemy, decorator)(owner, include="all")
        class OwnerInput: ...


@pytest.mark.extras
@pytest.mark.skipif(not find_spec("pydantic"), reason="pydantic is not installed")
def test_pydantic_write_model_with_relation_to_join_mapped_model_fail(strawchemy: Strawchemy) -> None:
    """Test that a pydantic validation model including a relation to a class mapped onto a join is rejected."""
    with pytest.raises(ReadOnlyModelError, match=re.escape(JOIN_MAPPED_ERROR_TEMPLATE.format("ColumnJoinedAB"))):

        @strawchemy.pydantic.create(ColumnJoinOwner, include="all")
        class OwnerValidation: ...


@pytest.mark.parametrize("decorator", ["create_input", "pk_update_input", "filter_update_input"])
def test_write_input_excluding_relation_to_join_mapped_model_accepted(strawchemy: Strawchemy, decorator: str) -> None:
    """Test that a write input leaving out its relation to a class mapped onto a join still builds."""

    @getattr(strawchemy, decorator)(ColumnJoinOwner, include="all", exclude=["items"])
    class OwnerInput: ...

    assert {field.name for field in get_object_definition(OwnerInput, strict=True).fields} == {"id"}


@pytest.mark.parametrize("kind", ["create", "update_by_ids", "update", "upsert", "delete_by_filter", "delete"])
def test_mutation_on_join_mapped_model_fail(strawchemy: Strawchemy, kind: str) -> None:
    """Test that a mutation returning a class mapped onto a join is rejected when its type is resolved."""

    @strawchemy.type(JoinedAB, include="all")
    class JoinedABType: ...

    @strawchemy.filter(JoinedAB, include="all")
    class JoinedABFilter: ...

    @strawchemy.create_input(Fruit, include="all")
    class FruitCreate: ...

    @strawchemy.pk_update_input(Fruit, include="all")
    class FruitUpdate: ...

    @strawchemy.filter_update_input(Fruit, include="all")
    class FruitPartial: ...

    @strawchemy.upsert_update_fields(Fruit, include="all")
    class FruitUpdateFields: ...

    @strawchemy.upsert_conflict_fields(Fruit, include="all")
    class FruitConflictFields: ...

    fields = {
        "create": lambda: strawchemy.create(FruitCreate),
        "update_by_ids": lambda: strawchemy.update_by_ids(FruitUpdate),
        "update": lambda: strawchemy.update(FruitPartial, JoinedABFilter),
        "upsert": lambda: strawchemy.upsert(FruitCreate, FruitUpdateFields, FruitConflictFields),
        "delete_by_filter": lambda: strawchemy.delete(JoinedABFilter),
        "delete": strawchemy.delete,
    }

    with pytest.raises(ReadOnlyModelError, match=JOIN_MAPPED_ERROR):

        @strawberry.type
        class Mutation:
            mutation: list[JoinedABType] = fields[kind]()


def test_mutation_with_resolver_on_join_mapped_model_accepted(strawchemy: Strawchemy) -> None:
    """Test that a mutation with a resolver can return a class mapped onto a join."""

    @strawchemy.type(JoinedAB, include="all")
    class JoinedABType: ...

    def resolve_delete() -> list[JoinedABType]:
        return []

    @strawberry.type
    class Mutation:
        delete_joined: list[JoinedABType] = strawchemy.delete(resolver=resolve_delete)

    assert "deleteJoined" in str(strawberry.Schema(query=DefaultQuery, mutation=Mutation))


def test_query_on_join_mapped_model_accepted(strawchemy: Strawchemy) -> None:
    """Test that read types, filters and query fields still build on a class mapped onto a join."""

    @strawchemy.type(JoinedAB, include="all")
    class JoinedABType: ...

    @strawchemy.filter(JoinedAB, include="all")
    class JoinedABFilter: ...

    @strawchemy.order(JoinedAB, include="all")
    class JoinedABOrder: ...

    @strawberry.type
    class Query:
        joined: list[JoinedABType] = strawchemy.field(filter_input=JoinedABFilter, order_by_input=JoinedABOrder)

    assert "joined(" in str(strawberry.Schema(query=Query))


def _field_named_type(graphql_schema: GraphQLSchema, type_name: str, *path: str) -> GraphQLNamedType:
    named = graphql_schema.get_type(type_name)
    for field_name in path:
        assert isinstance(named, (GraphQLObjectType, GraphQLInputObjectType))
        named = get_named_type(named.fields[field_name].type)
    assert named is not None
    return named


@pytest.mark.parametrize(
    "roots",
    [
        pytest.param(("create_input",), id="create"),
        pytest.param(("pk_update_input",), id="pk-update"),
        pytest.param(("filter_update_input",), id="filter-update"),
        pytest.param(("create_input", "pk_update_input"), id="create-then-pk-update"),
        pytest.param(("pk_update_input", "create_input"), id="pk-update-then-create"),
        pytest.param(("filter_update_input", "create_input"), id="filter-update-then-create"),
    ],
)
def test_nested_create_payload_has_create_shape(roots: tuple[str, ...]) -> None:
    """Test that the nested `create` payload of every root input has the create shape, whatever roots exist (#494)."""
    strawchemy = Strawchemy("postgresql")
    declared = {
        decorator: getattr(strawchemy, decorator)(Color, include="all")(
            type("Color" + "".join(part.title() for part in decorator.split("_")), (), {})
        )
        for decorator in roots
    }

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawchemy.filter(Color, include="all")
    class ColorFilter: ...

    fields: dict[str, Any] = {}
    annotations: dict[str, Any] = {}
    for decorator, input_type in declared.items():
        if decorator == "create_input":
            fields["create_color"], annotations["create_color"] = strawchemy.create(input_type), ColorType
        elif decorator == "pk_update_input":
            fields["update_color"], annotations["update_color"] = strawchemy.update_by_ids(input_type), ColorType
        else:
            fields["update_colors"] = strawchemy.update(input_type, ColorFilter)
            annotations["update_colors"] = list[ColorType]
    mutation = strawberry.type(type("Mutation", (), {"__annotations__": annotations, **fields}))
    graphql_schema = build_schema(str(strawberry.Schema(query=DefaultQuery, mutation=mutation)))

    for input_type in declared.values():
        payload = _field_named_type(graphql_schema, input_type.__name__, "fruits", "create")
        assert isinstance(payload, GraphQLInputObjectType)
        assert str(payload.fields["name"].type) == "String!", input_type.__name__
        assert str(payload.fields["id"].type) == "UUID", input_type.__name__


_FIELD_ARGUMENT_NAMES = {"paginate": {"limit", "offset"}, "order": {"orderBy"}, "distinct_on": {"distinctOn"}}


@pytest.mark.parametrize("option", sorted(_FIELD_ARGUMENT_NAMES))
@pytest.mark.parametrize("configured_first", [True, False])
def test_nested_relation_arguments_follow_their_root(option: str, configured_first: bool) -> None:
    """Test that nested relations get the field arguments of the root they are reached from, in either order (#518)."""
    strawchemy = Strawchemy("postgresql")

    def plain() -> type[Any]:
        return strawchemy.type(Container, include="all")(type("ContainerPlain", (), {}))

    def configured() -> type[Any]:
        return strawchemy.type(
            Container,
            include="all",
            paginate="all" if option == "paginate" else None,
            order="all" if option == "order" else None,
            distinct_on="all" if option == "distinct_on" else None,
        )(type("ContainerConfigured", (), {}))

    if configured_first:
        configured_type, plain_type = configured(), plain()
    else:
        plain_type, configured_type = plain(), configured()

    query = strawberry.type(
        type(
            "Query",
            (),
            {
                "__annotations__": {"plain": list[plain_type], "configured": list[configured_type]},  # ty: ignore[invalid-type-form]
                "plain": strawchemy.field(),
                "configured": strawchemy.field(),
            },
        )
    )
    graphql_schema = build_schema(str(strawberry.Schema(query=query)))
    expected = _FIELD_ARGUMENT_NAMES[option]

    for root, has_arguments in (("ContainerPlain", False), ("ContainerConfigured", True)):
        nested_color = _field_named_type(graphql_schema, root, "fruits", "color")
        assert isinstance(nested_color, GraphQLObjectType)
        assert (expected <= set(nested_color.fields["fruits"].args)) is has_arguments, root


@pytest.mark.parametrize("decorator", ["create_input", "pk_update_input", "filter_update_input"])
def test_nested_create_payload_back_reference_is_a_create_input(decorator: str) -> None:
    """Test that a nested `create` payload relating back to the root model nests a create input, not the root (#494)."""
    strawchemy = Strawchemy("postgresql")
    root = getattr(strawchemy, decorator)(TableMappedFruit, include="all")(type("FruitRoot", (), {}))

    @strawchemy.type(TableMappedFruit, include="all")
    class FruitType: ...

    @strawchemy.filter(TableMappedFruit, include="all")
    class FruitFilter: ...

    if decorator == "create_input":
        field: Any = strawchemy.create(root)
    elif decorator == "pk_update_input":
        field = strawchemy.update_by_ids(root)
    else:
        field = strawchemy.update(root, FruitFilter)
    mutation = strawberry.type(type("Mutation", (), {"__annotations__": {"mutate": list[FruitType]}, "mutate": field}))
    graphql_schema = build_schema(str(strawberry.Schema(query=DefaultQuery, mutation=mutation)))
    back_reference = _field_named_type(graphql_schema, "FruitRoot", "color", "create", "requiredFruit", "create")

    assert back_reference.description == "Create input"
    assert back_reference.name != "FruitRoot" or decorator == "create_input"


def test_generated_aggregate_count_enum_ignores_narrowed_declaration(strawchemy: Strawchemy) -> None:
    """Test that a narrowed aggregate filter leaves the generated count arguments enum model-wide (#493)."""

    @strawchemy.aggregate_filter(Fruit, include=["sweetness"], name="FruitSweetnessAggregate")
    class FruitSweetnessAggregate: ...

    @strawchemy.filter(Color, include="all")
    class ColorFilter: ...

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter)

    graphql_schema = build_schema(str(strawberry.Schema(query=Query)))
    count_fields = _field_named_type(graphql_schema, "ColorFilter", "fruitsAggregate", "count", "arguments")

    assert isinstance(count_fields, GraphQLEnumType)
    assert count_fields.name == "FruitCountFields"
    assert set(count_fields.values) == {"id", "name", "sweetness", "colorId"}


def test_field_distinct_on_lists_get_their_own_enums(strawchemy: Strawchemy) -> None:
    """Test that fields with different distinct_on lists each expose their own columns (#493)."""

    @strawchemy.type(Color, include="all")
    class ColorType: ...

    @strawberry.type
    class Query:
        colors_by_id: list[ColorType] = strawchemy.field(distinct_on=["id"])
        colors_by_name: list[ColorType] = strawchemy.field(distinct_on=["name"])

    query = build_schema(str(strawberry.Schema(query=Query))).get_type("Query")
    assert isinstance(query, GraphQLObjectType)
    by_id = get_named_type(query.fields["colorsById"].args["distinctOn"].type)
    by_name = get_named_type(query.fields["colorsByName"].args["distinctOn"].type)

    assert isinstance(by_id, GraphQLEnumType)
    assert isinstance(by_name, GraphQLEnumType)
    assert set(by_id.values) == {"id"}
    assert set(by_name.values) == {"name"}
