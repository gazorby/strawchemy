from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}]
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "best_time_to_pick": time(hour=9), "color_id": 1},
    {
        "id": 2,
        "name": "Cherry",
        "sweetness": 9,
        "water_percent": 0.93,
        "best_time_to_pick": time(hour=10, minute=30),
        "color_id": 1,
    },
    {
        "id": 3,
        "name": "Banana",
        "sweetness": 2,
        "water_percent": 0.75,
        "best_time_to_pick": time(hour=17, minute=15),
        "color_id": 2,
    },
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Color, include=["id", "name"])
    class PrivateNameColorType:
        name: strawberry.Private[str]

        @strawberry.field
        def upper_name(self) -> str:
            return self.name.upper()

    @strawchemy.type(Fruit, include=["id", "name", "color"])
    class PrivateNameFruitType:
        name: strawberry.Private[str]
        color: PrivateNameColorType | None

        @strawberry.field
        def upper_name(self) -> str:
            return self.name.upper()

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class PrivateNameColorWithFruitsType:
        name: strawberry.Private[str]
        fruits: list[PrivateNameFruitType]

        @strawberry.field
        def upper_name(self) -> str:
            return self.name.upper()

    @strawchemy.create_input(Fruit, include=["name", "sweetness", "water_percent", "color"])
    class FruitCreateInput: ...

    @strawchemy.pk_update_input(Fruit, include=["id", "name"])
    class FruitUpdateInput: ...

    @strawberry.type
    class Query:
        fruits_private_name: list[PrivateNameFruitType] = strawchemy.field()
        colors_private_name: list[PrivateNameColorWithFruitsType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_private_name_fruit: PrivateNameFruitType = strawchemy.create(FruitCreateInput)
        update_private_name_fruit: PrivateNameFruitType = strawchemy.update_by_ids(FruitUpdateInput)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


@pytest.mark.snapshot
async def test_private_column_is_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a private model column is loaded and readable by a resolver when it is not selected."""
    result = await maybe_async(any_query("{ fruitsPrivateName { id upperName } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruitsPrivateName"] == [
        {"id": to_graphql_representation(fruit["id"], "output"), "upperName": fruit["name"].upper()}
        for fruit in _FRUITS
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_private_column_of_to_one_relation_is_set(
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a private column of a to-one related type is loaded when only the relation is selected."""
    result = await maybe_async(any_query("{ fruitsPrivateName { id color { id upperName } } }"))

    assert not result.errors
    assert result.data
    colors = {color["id"]: color for color in _COLORS}
    assert result.data["fruitsPrivateName"] == [
        {
            "id": to_graphql_representation(fruit["id"], "output"),
            "color": {
                "id": to_graphql_representation(fruit["color_id"], "output"),
                "upperName": colors[fruit["color_id"]]["name"].upper(),
            },
        }
        for fruit in _FRUITS
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_private_column_of_to_many_relation_is_set(
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that private columns of a type and of its to-many related type are loaded in a single query."""
    result = await maybe_async(any_query("{ colorsPrivateName { id upperName fruits { upperName } } }"))

    assert not result.errors
    assert result.data
    assert [
        {**color, "fruits": sorted(fruit["upperName"] for fruit in color["fruits"])}
        for color in result.data["colorsPrivateName"]
    ] == [
        {
            "id": to_graphql_representation(color["id"], "output"),
            "upperName": color["name"].upper(),
            "fruits": sorted(fruit["name"].upper() for fruit in _FRUITS if fruit["color_id"] == color["id"]),
        }
        for color in _COLORS
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_returns_private_column(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a create mutation result type sets its private columns and those of its relations."""
    color_id = to_graphql_representation(_COLORS[0]["id"], "input")
    query = f"""
        mutation {{
            createPrivateNameFruit(data: {{
                name: "new fruit",
                sweetness: 1,
                waterPercent: 0.8,
                color: {{ set: {{ id: {color_id} }} }}
            }}) {{
                upperName
                color {{ upperName }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data
    assert result.data["createPrivateNameFruit"] == {
        "upperName": "NEW FRUIT",
        "color": {"upperName": _COLORS[0]["name"].upper()},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_returns_private_column(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that an update mutation result type sets its private columns."""
    fruit_id = to_graphql_representation(_FRUITS[0]["id"], "input")
    query = f"""
        mutation {{
            updatePrivateNameFruit(data: {{ id: {fruit_id}, name: "updated fruit" }}) {{
                upperName
            }}
        }}
    """
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data
    assert result.data["updatePrivateNameFruit"] == {"upperName": "UPDATED FRUIT"}

    query_tracker.assert_statements(1, "select", sql_snapshot)
