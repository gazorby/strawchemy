from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from strawberry import relay
from strawberry.types import get_object_definition
from strawberry.types.object_type import StrawberryObjectDefinition

from strawchemy import Strawchemy, StrawchemySyncRepository
from tests.unit.models import Fruit
from tests.utils import generate_query

strawchemy = Strawchemy("sqlite")


@strawchemy.type(Fruit, include=["id", "name"])
class PrivateFruitType:
    id: strawberry.Private[UUID]


@strawchemy.type(Fruit, include=["id", "name"])
class AnnotatedPrivateFruitType:
    id: Annotated[strawberry.Private[UUID], "metadata"]


@strawchemy.type(Fruit, include=["id", "name"])
class NodeIDFruitType:
    id: relay.NodeID[UUID]


@strawberry.type
class Query:
    private_fruits: list[PrivateFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)
    annotated_private_fruits: list[AnnotatedPrivateFruitType] = strawchemy.field(
        repository_type=StrawchemySyncRepository
    )
    node_id_fruits: list[NodeIDFruitType] = strawchemy.field(repository_type=StrawchemySyncRepository)


_FRUIT_TYPES = pytest.mark.parametrize(
    "fruit_type",
    [
        pytest.param(PrivateFruitType, id="private"),
        pytest.param(AnnotatedPrivateFruitType, id="annotated-private"),
        pytest.param(NodeIDFruitType, id="node-id"),
    ],
)


@_FRUIT_TYPES
def test_private_column_with_default_is_not_exposed(fruit_type: type[Any]) -> None:
    """Test that a private annotation on a column with a default keeps the column out of the GraphQL type."""
    type_name = get_object_definition(fruit_type, strict=True).name
    type_def = strawberry.Schema(query=Query).get_type_by_name(type_name)

    assert isinstance(type_def, StrawberryObjectDefinition)
    assert {field.name for field in type_def.fields} == {"name"}


@_FRUIT_TYPES
def test_private_column_with_default_is_set_on_instances(fruit_type: type[Any]) -> None:
    """Test that a private column with a default stays a constructor argument of the generated type."""
    fruit_id = uuid4()

    assert fruit_type(id=fruit_id, name="apple").id == fruit_id


@pytest.mark.parametrize("query_field", ["privateFruits", "annotatedPrivateFruits", "nodeIdFruits"])
def test_private_column_with_default_executes(query_field: str) -> None:
    """Test that a type with a private column with a default resolves rows from the database."""
    engine = create_engine("sqlite://")
    Fruit.metadata.create_all(engine, tables=[Fruit.metadata.tables[name] for name in ("color", "fruit")])
    with Session(engine) as session:
        session.add(Fruit(id=uuid4(), name="apple", sweetness=1, private="secret"))
        session.commit()

        result = generate_query(session, query=Query)(f"{{ {query_field} {{ name }} }}")

    assert not result.errors
    assert result.data == {query_field: [{"name": "apple"}]}
