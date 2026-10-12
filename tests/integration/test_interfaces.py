from __future__ import annotations

from datetime import time
from operator import itemgetter
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}]
_FRUITS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Apple",
        "sweetness": 4,
        "water_percent": 0.84,
        "best_time_to_pick": time(hour=9),
        "color_id": 1,
    },
    {
        "id": 2,
        "name": "Banana",
        "sweetness": 2,
        "water_percent": 0.75,
        "best_time_to_pick": time(hour=17, minute=15),
        "color_id": 2,
    },
]


@strawberry.interface
class Named:
    name: str


def _schema(strawchemy: Strawchemy) -> Operations:
    repository_type = strawchemy.config.repository_type

    @strawchemy.type(Color, include=["id", "name"])
    class NamedColorType(Named): ...

    @strawchemy.type(Fruit, include=["id", "name", "color"])
    class NamedFruitType(Named):
        color: NamedColorType | None

    @strawchemy.filter(Fruit, include=["name"])
    class NamedFruitFilter: ...

    @strawberry.type
    class AsyncQuery:
        fruits: list[NamedFruitType] = strawchemy.field(filter_input=NamedFruitFilter)

        @strawberry.field
        async def named(self, info: strawberry.Info) -> list[Named]:
            return [*(await StrawchemyAsyncRepository(NamedFruitType, info).list()).graphql_list()]

    @strawberry.type
    class SyncQuery:
        fruits: list[NamedFruitType] = strawchemy.field(filter_input=NamedFruitFilter)

        @strawberry.field
        def named(self, info: strawberry.Info) -> list[Named]:
            return [*StrawchemySyncRepository(NamedFruitType, info).list().graphql_list()]

    return Operations(query=AsyncQuery if issubclass(repository_type, StrawchemyAsyncRepository) else SyncQuery)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


def _color_names() -> dict[int, str]:
    return {color["id"]: color["name"] for color in _COLORS}


async def test_type_implementing_interface(any_query: AnyQueryExecutor) -> None:
    """Test that a type implementing an interface is queried, filtered and joined as its own type."""
    result = await maybe_async(
        any_query("""
            {
                fruits(filter: { name: { eq: "Apple" } }) {
                    __typename
                    name
                    color { __typename name }
                }
            }
        """)
    )

    assert not result.errors
    assert result.data
    apple = next(fruit for fruit in _FRUITS if fruit["name"] == "Apple")
    assert result.data["fruits"] == [
        {
            "__typename": "NamedFruitType",
            "name": "Apple",
            "color": {"__typename": "NamedColorType", "name": _color_names()[apple["color_id"]]},
        }
    ]


async def test_interface_field_resolves_implementing_type(any_query: AnyQueryExecutor) -> None:
    """Test that rows returned by an interface field resolve to the type implementing it."""
    result = await maybe_async(
        any_query("""
            {
                named {
                    __typename
                    name
                    ... on NamedFruitType { color { name } }
                }
            }
        """)
    )

    assert not result.errors
    assert result.data
    color_names = _color_names()
    expected = [
        {"__typename": "NamedFruitType", "name": fruit["name"], "color": {"name": color_names[fruit["color_id"]]}}
        for fruit in _FRUITS
    ]
    assert sorted(result.data["named"], key=itemgetter("name")) == sorted(expected, key=itemgetter("name"))
