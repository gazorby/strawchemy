from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any

import pytest
from strawchemy.exceptions import StrawchemyError

import strawberry
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry import auto
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition
from tests.models import Book as BookModel
from tests.models import User

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy


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
    from tests.unit.schemas.custom_resolver import ColorType, Query

    schema = strawberry.Schema(query=Query)
    type_def = schema.get_type_by_name("FruitType")
    assert isinstance(type_def, StrawberryObjectDefinition)
    field = type_def.get_field("color")
    assert field
    assert field.type is ColorType


def test_all_fields() -> None:
    from tests.unit.schemas.all_fields import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    input ColorAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateNumericFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateOrderBy {
      count: OrderByEnum
      sum: ColorAggregateNumericFieldsOrderBy
      minString: ColorAggregateMinMaxStringFieldsOrderBy
      maxString: ColorAggregateMinMaxStringFieldsOrderBy
    }

    """Ordering options"""
    input ColorOrderBy {
      id: OrderByEnum
      fruitsAggregate: FruitAggregateOrderBy
      fruits: FruitOrderBy
      name: OrderByEnum
    }

    """GraphQL type"""
    type ColorType {
      id: UUID!
      fruitsAggregate: FruitAggregate!

      """Fetch objects from the FruitType collection"""
      fruits(limit: Int = null, offset: Int = null, orderBy: [FruitOrderBy!] = null): [FruitType!]!
      name: String!
    }

    """Aggregation fields"""
    type FruitAggregate {
      count: Int!
      sum: FruitSumFields!
      min: FruitMinMaxFields!
      max: FruitMinMaxFields!
      avg: FruitNumericFields!
      stddev: FruitNumericFields!
      stddevSamp: FruitNumericFields!
      stddevPop: FruitNumericFields!
      variance: FruitNumericFields!
      varSamp: FruitNumericFields!
      varPop: FruitNumericFields!
    }

    input FruitAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input FruitAggregateNumericFieldsOrderBy {
      name: OrderByEnum
      sweetness: OrderByEnum
    }

    input FruitAggregateOrderBy {
      count: OrderByEnum
      sum: FruitAggregateNumericFieldsOrderBy
      min: FruitAggregateNumericFieldsOrderBy
      max: FruitAggregateNumericFieldsOrderBy
      minString: FruitAggregateMinMaxStringFieldsOrderBy
      maxString: FruitAggregateMinMaxStringFieldsOrderBy
      avg: FruitAggregateNumericFieldsOrderBy
      stddev: FruitAggregateNumericFieldsOrderBy
      stddevSamp: FruitAggregateNumericFieldsOrderBy
      stddevPop: FruitAggregateNumericFieldsOrderBy
      variance: FruitAggregateNumericFieldsOrderBy
      varSamp: FruitAggregateNumericFieldsOrderBy
      varPop: FruitAggregateNumericFieldsOrderBy
    }

    type FruitMinMaxFields {
      name: String!
      sweetness: Int!
    }

    type FruitNumericFields {
      sweetness: Int!
    }

    """Ordering options"""
    input FruitOrderBy {
      id: OrderByEnum
      name: OrderByEnum
      colorId: OrderByEnum
      colorAggregate: ColorAggregateOrderBy
      color: ColorOrderBy
      sweetness: OrderByEnum
    }

    type FruitSumFields {
      name: String!
      sweetness: Int!
    }

    """GraphQL type"""
    type FruitType {
      id: UUID!
      name: String!
      colorId: UUID
      color: ColorType!
      sweetness: Int!
    }

    enum OrderByEnum {
      ASC
      ASC_NULLS_FIRST
      ASC_NULLS_LAST
      DESC
      DESC_NULLS_FIRST
      DESC_NULLS_LAST
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_all_fields_override() -> None:
    from tests.unit.schemas.all_fields_override import Query

    schema = strawberry.Schema(query=Query)

    expected = '''\
    input ColorAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateNumericFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateOrderBy {
      count: OrderByEnum
      sum: ColorAggregateNumericFieldsOrderBy
      minString: ColorAggregateMinMaxStringFieldsOrderBy
      maxString: ColorAggregateMinMaxStringFieldsOrderBy
    }

    """Ordering options"""
    input ColorOrderBy {
      id: OrderByEnum
      fruitsAggregate: FruitAggregateOrderBy
      fruits: FruitOrderBy
      name: OrderByEnum
    }

    """GraphQL type"""
    type ColorType {
      id: UUID!
      fruitsAggregate: FruitAggregate!

      """Fetch objects from the FruitType collection"""
      fruits(limit: Int = null, offset: Int = null, orderBy: [FruitOrderBy!] = null): [FruitType!]!
      name: Int!
    }

    """Aggregation fields"""
    type FruitAggregate {
      count: Int!
      sum: FruitSumFields!
      min: FruitMinMaxFields!
      max: FruitMinMaxFields!
      avg: FruitNumericFields!
      stddev: FruitNumericFields!
      stddevSamp: FruitNumericFields!
      stddevPop: FruitNumericFields!
      variance: FruitNumericFields!
      varSamp: FruitNumericFields!
      varPop: FruitNumericFields!
    }

    input FruitAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input FruitAggregateNumericFieldsOrderBy {
      name: OrderByEnum
      sweetness: OrderByEnum
    }

    input FruitAggregateOrderBy {
      count: OrderByEnum
      sum: FruitAggregateNumericFieldsOrderBy
      min: FruitAggregateNumericFieldsOrderBy
      max: FruitAggregateNumericFieldsOrderBy
      minString: FruitAggregateMinMaxStringFieldsOrderBy
      maxString: FruitAggregateMinMaxStringFieldsOrderBy
      avg: FruitAggregateNumericFieldsOrderBy
      stddev: FruitAggregateNumericFieldsOrderBy
      stddevSamp: FruitAggregateNumericFieldsOrderBy
      stddevPop: FruitAggregateNumericFieldsOrderBy
      variance: FruitAggregateNumericFieldsOrderBy
      varSamp: FruitAggregateNumericFieldsOrderBy
      varPop: FruitAggregateNumericFieldsOrderBy
    }

    type FruitMinMaxFields {
      name: String!
      sweetness: Int!
    }

    type FruitNumericFields {
      sweetness: Int!
    }

    """Ordering options"""
    input FruitOrderBy {
      id: OrderByEnum
      name: OrderByEnum
      colorId: OrderByEnum
      colorAggregate: ColorAggregateOrderBy
      color: ColorOrderBy
      sweetness: OrderByEnum
    }

    type FruitSumFields {
      name: String!
      sweetness: Int!
    }

    """GraphQL type"""
    type FruitType {
      name: Int!
      id: UUID!
      colorId: UUID
      color: ColorType!
      sweetness: Int!
    }

    enum OrderByEnum {
      ASC
      ASC_NULLS_FIRST
      ASC_NULLS_LAST
      DESC
      DESC_NULLS_FIRST
      DESC_NULLS_LAST
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_include_fields() -> None:
    from tests.unit.schemas.include_explicit import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type FruitType {
      name: String!
      sweetness: Int!
    }

    type Query {
      fruit: FruitType!
    }
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_exclude_exclude() -> None:
    from tests.unit.schemas.exclude_explicit import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type FruitType {
      id: UUID!
      name: String!
      sweetness: Int!
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_include_non_existent_fields_ignored() -> None:
    from tests.unit.schemas.include_non_existent import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type FruitType {
      name: String!
    }

    type Query {
      fruit: FruitType!
    }
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_exclude_non_existent_fields_ignored() -> None:
    from tests.unit.schemas.exclude_non_existent import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type FruitType {
      id: UUID!
      name: String!
      sweetness: Int!
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_auto_primary_key_resolver() -> None:
    from tests.unit.schemas.primary_key_resolver import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type ColorType {
      id: UUID!
      name: String!
    }

    """GraphQL type"""
    type FruitType {
      color: ColorType!
      name: String!
    }

    type Query {
      """Fetch object from the FruitType collection by id"""
      fruit(id: UUID!): FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_auto_list_resolver() -> None:
    from tests.unit.schemas.list_resolver import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type ColorType {
      id: UUID!
      name: String!
    }

    """GraphQL type"""
    type FruitType {
      color: ColorType!
      name: String!
    }

    type Query {
      """Fetch objects from the FruitType collection"""
      fruit(limit: Int = null, offset: Int = null): [FruitType!]!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_can_override_type_with_exclude() -> None:
    from tests.unit.schemas.exclude_and_override_type import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    input ColorAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateNumericFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateOrderBy {
      count: OrderByEnum
      sum: ColorAggregateNumericFieldsOrderBy
      minString: ColorAggregateMinMaxStringFieldsOrderBy
      maxString: ColorAggregateMinMaxStringFieldsOrderBy
    }

    """Ordering options"""
    input ColorOrderBy {
      id: OrderByEnum
      fruitsAggregate: FruitAggregateOrderBy
      fruits: FruitOrderBy
      name: OrderByEnum
    }

    """GraphQL type"""
    type ColorType {
      id: UUID!
      fruitsAggregate: FruitAggregate!

      """Fetch objects from the FruitType collection"""
      fruits(limit: Int = null, offset: Int = null, orderBy: [FruitOrderBy!] = null): [FruitType!]!
      name: String!
    }

    """Aggregation fields"""
    type FruitAggregate {
      count: Int!
      sum: FruitSumFields!
      min: FruitMinMaxFields!
      max: FruitMinMaxFields!
      avg: FruitNumericFields!
      stddev: FruitNumericFields!
      stddevSamp: FruitNumericFields!
      stddevPop: FruitNumericFields!
      variance: FruitNumericFields!
      varSamp: FruitNumericFields!
      varPop: FruitNumericFields!
    }

    input FruitAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input FruitAggregateNumericFieldsOrderBy {
      name: OrderByEnum
      sweetness: OrderByEnum
    }

    input FruitAggregateOrderBy {
      count: OrderByEnum
      sum: FruitAggregateNumericFieldsOrderBy
      min: FruitAggregateNumericFieldsOrderBy
      max: FruitAggregateNumericFieldsOrderBy
      minString: FruitAggregateMinMaxStringFieldsOrderBy
      maxString: FruitAggregateMinMaxStringFieldsOrderBy
      avg: FruitAggregateNumericFieldsOrderBy
      stddev: FruitAggregateNumericFieldsOrderBy
      stddevSamp: FruitAggregateNumericFieldsOrderBy
      stddevPop: FruitAggregateNumericFieldsOrderBy
      variance: FruitAggregateNumericFieldsOrderBy
      varSamp: FruitAggregateNumericFieldsOrderBy
      varPop: FruitAggregateNumericFieldsOrderBy
    }

    type FruitMinMaxFields {
      sweetness: Int!
    }

    type FruitNumericFields {
      sweetness: Int!
    }

    """Ordering options"""
    input FruitOrderBy {
      id: OrderByEnum
      name: OrderByEnum
      colorId: OrderByEnum
      colorAggregate: ColorAggregateOrderBy
      color: ColorOrderBy
      sweetness: OrderByEnum
    }

    type FruitSumFields {
      sweetness: Int!
    }

    """GraphQL type"""
    type FruitType {
      sweetness: String!
      id: UUID!
      colorId: UUID
      color: ColorType!
    }

    enum OrderByEnum {
      ASC
      ASC_NULLS_FIRST
      ASC_NULLS_LAST
      DESC
      DESC_NULLS_FIRST
      DESC_NULLS_LAST
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_can_override_fields_with_exclude() -> None:
    from tests.unit.schemas.exclude_and_override_field import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    input ColorAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateNumericFieldsOrderBy {
      name: OrderByEnum
    }

    input ColorAggregateOrderBy {
      count: OrderByEnum
      sum: ColorAggregateNumericFieldsOrderBy
      minString: ColorAggregateMinMaxStringFieldsOrderBy
      maxString: ColorAggregateMinMaxStringFieldsOrderBy
    }

    """Ordering options"""
    input ColorOrderBy {
      id: OrderByEnum
      fruitsAggregate: FruitAggregateOrderBy
      fruits: FruitOrderBy
      name: OrderByEnum
    }

    """GraphQL type"""
    type ColorType {
      id: UUID!
      fruitsAggregate: FruitAggregate!

      """Fetch objects from the FruitType collection"""
      fruits(limit: Int = null, offset: Int = null, orderBy: [FruitOrderBy!] = null): [FruitType!]!
      name: String!
    }

    """Aggregation fields"""
    type FruitAggregate {
      count: Int!
      sum: FruitSumFields!
      min: FruitMinMaxFields!
      max: FruitMinMaxFields!
      avg: FruitNumericFields!
      stddev: FruitNumericFields!
      stddevSamp: FruitNumericFields!
      stddevPop: FruitNumericFields!
      variance: FruitNumericFields!
      varSamp: FruitNumericFields!
      varPop: FruitNumericFields!
    }

    input FruitAggregateMinMaxStringFieldsOrderBy {
      name: OrderByEnum
    }

    input FruitAggregateNumericFieldsOrderBy {
      name: OrderByEnum
      sweetness: OrderByEnum
    }

    input FruitAggregateOrderBy {
      count: OrderByEnum
      sum: FruitAggregateNumericFieldsOrderBy
      min: FruitAggregateNumericFieldsOrderBy
      max: FruitAggregateNumericFieldsOrderBy
      minString: FruitAggregateMinMaxStringFieldsOrderBy
      maxString: FruitAggregateMinMaxStringFieldsOrderBy
      avg: FruitAggregateNumericFieldsOrderBy
      stddev: FruitAggregateNumericFieldsOrderBy
      stddevSamp: FruitAggregateNumericFieldsOrderBy
      stddevPop: FruitAggregateNumericFieldsOrderBy
      variance: FruitAggregateNumericFieldsOrderBy
      varSamp: FruitAggregateNumericFieldsOrderBy
      varPop: FruitAggregateNumericFieldsOrderBy
    }

    type FruitMinMaxFields {
      sweetness: Int!
    }

    type FruitNumericFields {
      sweetness: Int!
    }

    """Ordering options"""
    input FruitOrderBy {
      id: OrderByEnum
      name: OrderByEnum
      colorId: OrderByEnum
      colorAggregate: ColorAggregateOrderBy
      color: ColorOrderBy
      sweetness: OrderByEnum
    }

    type FruitSumFields {
      sweetness: Int!
    }

    """GraphQL type"""
    type FruitType {
      id: UUID!
      name: String!
      colorId: UUID
      color: ColorType!
      sweetness: Int!
    }

    enum OrderByEnum {
      ASC
      ASC_NULLS_FIRST
      ASC_NULLS_LAST
      DESC
      DESC_NULLS_FIRST
      DESC_NULLS_LAST
    }

    type Query {
      fruit: FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_type_override() -> None:
    from tests.unit.schemas.type_override import Query

    schema = strawberry.Schema(query=Query)
    expected = '''\
    """GraphQL type"""
    type ColorType {
      id: UUID!
      fruitsAggregate: FruitAggregate!

      """Fetch object from the FruitType collection by id"""
      fruits(id: UUID!): FruitType!
      name: String!
    }

    """Aggregation fields"""
    type FruitAggregate {
      count: Int!
      sum: FruitSumFields!
      min: FruitMinMaxFields!
      max: FruitMinMaxFields!
      avg: FruitNumericFields!
      stddev: FruitNumericFields!
      stddevSamp: FruitNumericFields!
      stddevPop: FruitNumericFields!
      variance: FruitNumericFields!
      varSamp: FruitNumericFields!
      varPop: FruitNumericFields!
    }

    type FruitMinMaxFields {
      name: String!
      sweetness: Int!
    }

    type FruitNumericFields {
      sweetness: Int!
    }

    type FruitSumFields {
      name: String!
      sweetness: Int!
    }

    """GraphQL type"""
    type FruitType {
      name: Int!
      color: ColorType!
    }

    type Query {
      """Fetch object from the FruitType collection by id"""
      fruit(id: UUID!): FruitType!
    }

    scalar UUID
    '''

    assert textwrap.dedent(str(schema)) == textwrap.dedent(expected).strip()


def test_multiple_types_error() -> None:
    with pytest.raises(
        StrawchemyError,
        match=(
            """Type `FruitType` cannot be auto generated because it's already explicitly declared."""
            """ Either use `override=True` on the explicit type to use it everywhere, or use override `FruitType` fields where needed"""
        ),
    ):
        from tests.unit.schemas import multiple_types  # noqa: F401 # pyright: ignore[reportUnusedImport]
