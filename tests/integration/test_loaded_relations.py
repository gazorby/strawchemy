from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert, select
from sqlalchemy.orm import selectinload
from typing_extensions import override

from strawchemy import ModelInstance, QueryHook
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.util import AliasedClass

    from strawchemy import Strawchemy
    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SelectOf, SupportedDialect
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
    {
        "id": 4,
        "name": "Lemon",
        "sweetness": 1,
        "water_percent": 0.88,
        "best_time_to_pick": time(hour=20),
        "color_id": 2,
    },
    {
        "id": 5,
        "name": "Quince",
        "sweetness": 3,
        "water_percent": 0.81,
        "best_time_to_pick": time(hour=13),
        "color_id": 2,
    },
]
# Apple has two farms and Cherry one: the hook loads the farms of both, while the selection keeps only Apple,
# so the two farm sets differ.
_FARMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Cherry farm", "fruit_id": 2},
    {"id": 4, "name": "Banana farm", "fruit_id": 3},
]


class _FruitFilterHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        if self.info.context.role == "user":
            return statement.where(alias.name == "Apple")
        return statement


class _SweetFruitHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.where(alias.sweetness > 5)


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "sweetness", "color"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "fruits"], order=["id", "fruits"], scope="schema")
    class ColorType: ...

    @strawchemy.type(Color, include=["id", "fruits"], order=["id", "fruits"], paginate=["fruits"])
    class ColorTypeWithPagination: ...

    @strawchemy.type(Color, include=["id", "fruits"])
    class ColorWithSweetFruits:
        fruits: list[FruitType] = strawchemy.field(query_hook=_SweetFruitHook())

    @strawchemy.type(Fruit, include=["id", "name"], query_hook=_FruitFilterHook())
    class FilteredFruitType: ...

    @strawchemy.type(Color, include=["id", "fruits"])
    class ColorWithFilteredFruit:
        instance: ModelInstance[Color]

        fruits: list[FilteredFruitType]

        @strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [(Fruit.farms, [FruitFarm.name])])]))
        def farms(self) -> str:
            return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"

    @strawchemy.create_input(Fruit, include=["name", "sweetness", "water_percent", "color"])
    class FruitCreateInput: ...

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field()
        colors: list[ColorType] = strawchemy.field()
        colors_paginated: list[ColorTypeWithPagination] = strawchemy.field(pagination=True)
        colors_with_sweet_fruits: list[ColorWithSweetFruits] = strawchemy.field()
        colors_with_filtered_fruits: list[ColorWithFilteredFruit] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_fruit: FruitType = strawchemy.create(FruitCreateInput)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FARMS)]


async def _data(any_async_query: AnyQueryExecutor, query: str) -> dict[str, Any]:
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    return result.data


def _sweetness_of(color_id: int, *, descending: bool = False) -> list[int]:
    return sorted((fruit["sweetness"] for fruit in _FRUITS if fruit["color_id"] == color_id), reverse=descending)


async def _load_colors_with_fruits(any_async_session: AnySession) -> Sequence[Color]:
    result = await maybe_async(any_async_session.execute(select(Color).options(selectinload(Color.fruits))))
    return result.scalars().all()


async def test_nested_order_by_ignores_collection_loaded_in_session(
    any_async_query: AnyQueryExecutor,
    any_async_session: AnySession,
    query_tracker: QueryTracker,
) -> None:
    """Test that a nested relation is ordered as asked when the session already holds that collection."""
    await _data(any_async_query, "{ colors { id } }")
    kept = await _load_colors_with_fruits(any_async_session)
    kept_fruits = {color.id: [fruit.id for fruit in color.fruits] for color in kept}
    query_tracker.executions.clear()

    data = await _data(any_async_query, "{ colors { id fruits(orderBy: { sweetness: DESC }) { sweetness } } }")

    assert query_tracker.query_count == 1
    for color in data["colors"]:
        expected = _sweetness_of(color["id"], descending=True)
        assert [fruit["sweetness"] for fruit in color["fruits"]] == expected
    assert {color.id: [fruit.id for fruit in color.fruits] for color in kept} == kept_fruits


async def test_nested_pagination_ignores_collection_loaded_in_session(
    any_async_query: AnyQueryExecutor, any_async_session: AnySession
) -> None:
    """Test that a nested relation is paginated as asked when the session already holds that collection."""
    kept = await _load_colors_with_fruits(any_async_session)

    data = await _data(
        any_async_query,
        "{ colorsPaginated { id fruits(orderBy: { sweetness: DESC }, limit: 1, offset: 1) { sweetness } } }",
    )

    assert kept
    for color in data["colorsPaginated"]:
        expected = _sweetness_of(color["id"], descending=True)[1:2]
        assert [fruit["sweetness"] for fruit in color["fruits"]] == expected


async def test_nested_filter_ignores_collection_loaded_in_session(
    any_async_query: AnyQueryExecutor, any_async_session: AnySession
) -> None:
    """Test that a nested relation is filtered as asked when the session already holds that collection."""
    kept = await _load_colors_with_fruits(any_async_session)

    data = await _data(any_async_query, "{ colorsWithSweetFruits { id fruits { sweetness } } }")

    assert kept
    for color in data["colorsWithSweetFruits"]:
        expected = [sweetness for sweetness in _sweetness_of(color["id"]) if sweetness > 5]
        assert sorted(fruit["sweetness"] for fruit in color["fruits"]) == expected


async def test_to_one_relation_ignores_stale_attribute_loaded_in_session(
    any_query: AnyQueryExecutor,
    any_session: AnySession,
) -> None:
    """Test that a to-one relation follows the foreign key when the session holds the previously related object."""
    fruit_id = _FRUITS[0]["id"]
    new_color_id = next(color["id"] for color in _COLORS if color["id"] != _FRUITS[0]["color_id"])
    result = await maybe_async(
        any_session.execute(select(Fruit).options(selectinload(Fruit.color)).where(Fruit.id == fruit_id))
    )
    fruit = result.scalar_one()
    fruit.color_id = new_color_id
    await maybe_async(any_session.flush())

    data = await _data(any_query, "{ fruits { id color { id } } }")

    assert next(item for item in data["fruits"] if item["id"] == fruit_id)["color"] == {"id": new_color_id}


@pytest.mark.allow_duplicate_reads(
    reason=(
        "on postgresql, colors.fruits (sweetness DESC) and colors.fruits.color.fruits (sweetness ASC) each read "
        "fruit through their own LATERAL, two-path selections staying separate there; the CTE databases merge "
        "their rank CTEs"
    ),
    dialects=("postgresql",),
)
async def test_same_object_reached_through_two_paths_keeps_each_path_arguments(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a model reached through two selection paths with different arguments gets each path's collection."""
    data = await _data(
        any_async_query,
        """
        {
            colors {
                id
                fruits(orderBy: { sweetness: DESC }) {
                    sweetness
                    color { id fruits(orderBy: { sweetness: ASC }) { sweetness } }
                }
            }
        }
        """,
    )

    assert query_tracker.query_count == 1
    for color in data["colors"]:
        assert [fruit["sweetness"] for fruit in color["fruits"]] == _sweetness_of(color["id"], descending=True)
        for fruit in color["fruits"]:
            nested = fruit["color"]
            assert [related["sweetness"] for related in nested["fruits"]] == _sweetness_of(nested["id"])


async def test_same_object_reached_through_two_paths_keeps_each_path_filter(any_async_query: AnyQueryExecutor) -> None:
    """Test that a model reached through a filtered and an unfiltered selection path gets each path's collection."""
    data = await _data(
        any_async_query,
        """
        {
            colorsWithSweetFruits {
                id
                fruits { sweetness color { id fruits { sweetness } } }
            }
        }
        """,
    )

    for color in data["colorsWithSweetFruits"]:
        ascending = _sweetness_of(color["id"])
        assert sorted(fruit["sweetness"] for fruit in color["fruits"]) == [value for value in ascending if value > 5]
        for fruit in color["fruits"]:
            assert sorted(related["sweetness"] for related in fruit["color"]["fruits"]) == ascending


async def test_relation_selected_and_loaded_by_query_hook(any_async_query: AnyQueryExecutor) -> None:
    """Test that a relation both selected and loaded by a query hook gets the selection's rows and the hook's."""
    data = await _data(any_async_query, "{ colorsWithFilteredFruits { id fruits { name } farms } }")

    assert {color["id"] for color in data["colorsWithFilteredFruits"]} == {color["id"] for color in _COLORS}
    for color in data["colorsWithFilteredFruits"]:
        fruits = [fruit for fruit in _FRUITS if fruit["color_id"] == color["id"]]
        fruit_ids = {fruit["id"] for fruit in fruits}
        farm_names = sorted(farm["name"] for farm in _FARMS if farm["fruit_id"] in fruit_ids)
        assert color["fruits"] == [{"name": fruit["name"]} for fruit in fruits if fruit["name"] == "Apple"]
        assert sorted(color["farms"].removeprefix("Farms are: ").split(", ")) == farm_names


async def test_mutation_result_ignores_collection_loaded_in_session(
    any_async_query: AnyQueryExecutor,
    any_async_session: AnySession,
) -> None:
    """Test that a mutation result lists the created object when the session already holds the parent collection."""
    color_id = _COLORS[0]["id"]
    kept = await _load_colors_with_fruits(any_async_session)

    data = await _data(
        any_async_query,
        f"""
        mutation {{
            createFruit(data: {{
                name: "new fruit",
                sweetness: 1,
                waterPercent: 0.8,
                color: {{ set: {{ id: {to_graphql_representation(color_id, "input")} }} }}
            }}) {{
                color {{ fruits {{ name }} }}
            }}
        }}
        """,
    )

    assert kept
    expected = sorted([*(fruit["name"] for fruit in _FRUITS if fruit["color_id"] == color_id), "new fruit"])
    assert sorted(fruit["name"] for fruit in data["createFruit"]["color"]["fruits"]) == expected
