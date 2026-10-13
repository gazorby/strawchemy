from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert
from sqlalchemy.orm import aliased
from typing_extensions import override

from strawchemy import ModelInstance, QueryHook
from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.util import AliasedClass
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.transpiler.hook import LoadType
    from strawchemy.typing import SelectOf, SupportedDialect
    from tests.integration.fixtures import QueryTracker

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Orange"},
    {"id": 4, "name": "Green"},
    {"id": 5, "name": "Pink"},
]
# Every fruit and color is kept because several cases pin literal name lists.
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 1, "water_percent": 0.88, "color_id": 2},
    {"id": 5, "name": "Quince", "sweetness": 3, "water_percent": 0.81, "color_id": 2},
    {"id": 6, "name": "Orange", "sweetness": 8, "water_percent": 0.86, "color_id": 3},
    {"id": 7, "name": "clementine", "sweetness": 14, "water_percent": 0.9, "color_id": 3},
    {"id": 8, "name": "Strawberry", "sweetness": 5, "water_percent": 0.91, "color_id": 4},
    {"id": 9, "name": "Cantaloupe", "sweetness": 0, "water_percent": 0.51, "color_id": 4},
    {"id": 10, "name": "Watermelon", "sweetness": 7, "water_percent": 0.92, "color_id": 5},
    {"id": 11, "name": "Pears", "sweetness": 11, "water_percent": 0.15, "color_id": 5},
]
# Every fruit needs a farm for the farm-loading hooks; only Apple and Cherry get a " 2" farm for `_MultiFarmFruitHook`.
_FARMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Cherry farm", "fruit_id": 2},
    {"id": 4, "name": "Cherry farm 2", "fruit_id": 2},
    {"id": 5, "name": "Banana farm", "fruit_id": 3},
    {"id": 6, "name": "Lemon farm", "fruit_id": 4},
    {"id": 7, "name": "Quince farm", "fruit_id": 5},
    {"id": 8, "name": "Orange farm", "fruit_id": 6},
    {"id": 9, "name": "clementine farm", "fruit_id": 7},
    {"id": 10, "name": "Strawberry farm", "fruit_id": 8},
    {"id": 11, "name": "Cantaloupe farm", "fruit_id": 9},
    {"id": 12, "name": "Watermelon farm", "fruit_id": 10},
    {"id": 13, "name": "Pears farm", "fruit_id": 11},
]


class _FruitFilterHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        if self.info.context.role == "user":
            return statement.where(alias.name == "Apple")
        return statement


class _FruitOrderingHook(QueryHook[Fruit]):
    load: Sequence[LoadType] = [Fruit.water_percent]

    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.order_by(alias.water_percent.asc())


class _SweetFruitHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.where(alias.sweetness > 5)


class _MultiFarmFruitHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        return statement.join(FruitFarm, FruitFarm.fruit_id == alias.id).where(FruitFarm.name.endswith(" 2"))


class _FruitColorNameOrderingHook(QueryHook[Fruit]):
    @override
    def apply_hook(self, statement: SelectOf[Fruit], alias: AliasedClass[Fruit]) -> SelectOf[Fruit]:
        color = aliased(Color)
        return statement.outerjoin(color, color.id == alias.color_id).order_by(color.name.desc())


class _ColorOrderingHook(QueryHook[Color]):
    @override
    def apply_hook(self, statement: SelectOf[Color], alias: AliasedClass[Color]) -> SelectOf[Color]:
        return statement.order_by(alias.name.asc())


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Fruit, include=["id"])
    class FruitTypeHooks:
        instance: ModelInstance[Fruit]

        @strawchemy.field(query_hook=QueryHook(load=[Fruit.name, Fruit.color_id]))
        def description(self) -> str:
            return self.instance.description

        @strawchemy.field(query_hook=QueryHook())
        def empty_query_hook(self) -> str:
            return "success"

        @strawchemy.field(query_hook=QueryHook(load=[(Fruit.color, [Color.name, Color.created_at])]))
        def pretty_color(self) -> str:
            return f"Color is {self.instance.color.name}" if self.instance.color else "No color!"

        @strawchemy.field(query_hook=QueryHook(load=[Fruit.farms]))
        def pretty_farms(self) -> str:
            return (
                f"Farms are: {', '.join(farm.name for farm in self.instance.farms)}"
                if self.instance.farms
                else "No farm!"
            )

    @strawchemy.type(Fruit, include=["id", "name"], query_hook=_FruitFilterHook())
    class FilteredFruitType: ...

    @strawchemy.type(Fruit, include=["id", "name", "sweetness", "water_percent"], query_hook=_FruitOrderingHook())
    class OrderedFruitType: ...

    @strawchemy.type(Fruit, include=["id", "name"], query_hook=_FruitColorNameOrderingHook())
    class ColorNameOrderedFruitType: ...

    @strawchemy.aggregate(Fruit, include=["name"])
    class FruitAggregationType: ...

    @strawchemy.order(Fruit, include=["sweetness"])
    class FruitOrderBy: ...

    @strawchemy.distinct_on(Fruit, include=["color_id"])
    class FruitDistinctOn: ...

    @strawchemy.filter(Color, include=["fruits", "name", "sweetness"])
    class ColorFilter: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithFilteredFruit:
        instance: ModelInstance[Color]

        fruits: list[FilteredFruitType]

        @strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [(Fruit.farms, [FruitFarm.name])])]))
        def farms(self) -> str:
            return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"

        @strawchemy.field(query_hook=QueryHook(load=[(Color.fruits, [Fruit.farms])]))
        def farms_no_columns(self) -> str:
            return f"Farms are: {', '.join(farm.name for fruit in self.instance.fruits for farm in fruit.farms)}"

    @strawchemy.type(Color, include=["id", "fruits"])
    class ColorTypeHooks:
        fruits: list[FruitTypeHooks]

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithSweetFruits:
        fruits: list[FruitType] = strawchemy.field(query_hook=_SweetFruitHook())

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithPaginatedSweetFruits:
        fruits: list[FruitType] = strawchemy.field(
            query_hook=_SweetFruitHook(load=[Fruit.water_percent]), pagination=True
        )

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithMultiFarmFruits:
        fruits: list[FruitType] = strawchemy.field(query_hook=_MultiFarmFruitHook())

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithOrderedFruits:
        fruits: list[OrderedFruitType] = strawchemy.field(order_by_input=FruitOrderBy)

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithColorNameOrderedFruits:
        fruits: list[ColorNameOrderedFruitType] = strawchemy.field(
            order_by_input=FruitOrderBy, distinct_on=FruitDistinctOn
        )

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorWithPaginatedOrderedFruits:
        fruits: list[OrderedFruitType] = strawchemy.field(pagination=True)

    @strawchemy.type(Color, include=["id", "name", "fruits"], query_hook=_ColorOrderingHook())
    class OrderedColorType: ...

    @strawchemy.type(Fruit, include=["id", "color"], order=["name", "color", "fruits"])
    class FruitWithOrderedColorType:
        color: OrderedColorType | None

    @strawberry.type
    class Query:
        fruits_hooks: list[FruitTypeHooks] = strawchemy.field()
        fruits_paginated_hooks: list[FruitTypeHooks] = strawchemy.field(pagination=True)
        filtered_fruits: list[FilteredFruitType] = strawchemy.field()
        filtered_fruits_paginated: list[FilteredFruitType] = strawchemy.field(pagination=True)
        ordered_fruits: list[OrderedFruitType] = strawchemy.field()
        ordered_fruits_paginated: list[OrderedFruitType] = strawchemy.field(pagination=True)
        field_filtered_fruits: list[FruitType] = strawchemy.field(query_hook=_FruitFilterHook())
        field_filtered_fruits_paginated: list[FruitType] = strawchemy.field(
            query_hook=_FruitFilterHook(), pagination=True
        )
        field_filtered_fruit: FruitType | None = strawchemy.field(query_hook=_FruitFilterHook())
        field_filtered_fruit_aggregations: FruitAggregationType = strawchemy.field(
            query_hook=_FruitFilterHook(), root_aggregations=True
        )
        field_load_fruits: list[FruitType] = strawchemy.field(query_hook=QueryHook(load=[Fruit.water_percent]))
        colors_with_filtered_fruits: list[ColorWithFilteredFruit] = strawchemy.field()
        colors_with_filtered_fruits_paginated: list[ColorWithFilteredFruit] = strawchemy.field(pagination=True)
        colors_hooks: list[ColorTypeHooks] = strawchemy.field()
        colors_hooks_paginated: list[ColorTypeHooks] = strawchemy.field(pagination=True)
        colors_with_sweet_fruits: list[ColorWithSweetFruits] = strawchemy.field(filter_input=ColorFilter)
        colors_with_sweet_fruits_paginated: list[ColorWithSweetFruits] = strawchemy.field(
            filter_input=ColorFilter, pagination=True
        )
        colors_with_paginated_sweet_fruits: list[ColorWithPaginatedSweetFruits] = strawchemy.field()
        colors_with_multi_farm_fruits: list[ColorWithMultiFarmFruits] = strawchemy.field(filter_input=ColorFilter)
        colors_with_ordered_fruits: list[ColorWithOrderedFruits] = strawchemy.field()
        fruits_with_ordered_color: list[FruitWithOrderedColorType] = strawchemy.field()
        fruits_with_ordered_color_paginated: list[FruitWithOrderedColorType] = strawchemy.field(pagination=True)
        colors_with_paginated_ordered_fruits: list[ColorWithPaginatedOrderedFruits] = strawchemy.field()
        colors_with_color_name_ordered_fruits: list[ColorWithColorNameOrderedFruits] = strawchemy.field()
        color_name_ordered_fruits: list[ColorNameOrderedFruitType] = strawchemy.field(
            order_by_input=FruitOrderBy, distinct_on=FruitDistinctOn
        )
        color_name_ordered_fruits_paginated: list[ColorNameOrderedFruitType] = strawchemy.field(
            order_by_input=FruitOrderBy, distinct_on=FruitDistinctOn, pagination=True
        )

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FARMS)]


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_columns_hook(
    fruits_query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {fruits_query} {{ description }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"description": f"The {fruit['name']} color id is {fruit['color_id']}"} for fruit in _FRUITS
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_relationships_with_columns(
    fruits_query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {fruits_query} {{ prettyColor }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"prettyColor": f"Color is {next(color['name'] for color in _COLORS if color['id'] == fruit['color_id'])}"}
        for fruit in _FRUITS
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_relationships_no_columns(
    fruits_query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {fruits_query} {{ prettyFarms }} }}"))

    assert not result.errors
    assert result.data
    farm_names = [", ".join(farm["name"] for farm in _FARMS if farm["fruit_id"] == fruit["id"]) for fruit in _FRUITS]
    assert result.data[fruits_query] == [{"prettyFarms": f"Farms are: {name}"} for name in farm_names]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsWithFilteredFruits", "colorsWithFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_nested(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {query} {{ farms }} }}"))

    assert not result.errors
    assert result.data

    # The query asks for no ordering, so the farms of a fruit come back in a dialect-dependent order.
    farm_names = [
        sorted(
            farm["name"]
            for fruit in _FRUITS
            if fruit["color_id"] == color["id"]
            for farm in _FARMS
            if farm["fruit_id"] == fruit["id"]
        )
        for color in _COLORS
    ]
    assert [
        sorted(entry["farms"].removeprefix("Farms are: ").split(", ")) for entry in result.data[query]
    ] == farm_names

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsWithFilteredFruits", "colorsWithFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_load_nested_relationships_no_columns(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {query} {{ farmsNoColumns }} }}"))

    assert not result.errors
    assert result.data

    farm_names = [
        sorted(
            farm["name"]
            for fruit in _FRUITS
            if fruit["color_id"] == color["id"]
            for farm in _FARMS
            if farm["fruit_id"] == fruit["id"]
        )
        for color in _COLORS
    ]
    assert [
        sorted(entry["farmsNoColumns"].removeprefix("Farms are: ").split(", ")) for entry in result.data[query]
    ] == farm_names

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsHooks", "colorsHooksPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_on_nested_field(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {query} {{ id fruits {{ prettyColor }} }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[query] == [
        {
            "id": color["id"],
            "fruits": [
                {"prettyColor": f"Color is {color['name']}"}
                for _ in range(len([fruit for fruit in _FRUITS if fruit["color_id"] == color["id"]]))
            ],
        }
        for color in _COLORS
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
async def test_empty_query_hook(fruits_query: str, any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query(f"{{ {fruits_query} {{ emptyQueryHook }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[fruits_query]) == len(_FRUITS)
    assert result.data[fruits_query] == [{"emptyQueryHook": "success"} for _ in range(len(_FRUITS))]


@pytest.mark.parametrize("query", ["filteredFruits", "filteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_where(
    query: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == 1
    assert result.data[query] == [{"name": "Apple"}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["filteredFruits", "filteredFruitsPaginated", "fieldFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_where_on_unselected_column(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root query hook filters on a column the query does not select."""
    result = await maybe_async(any_async_query(f"{{ {query} {{ id }} }}"))

    assert not result.errors
    assert result.data
    apple_id = next(fruit["id"] for fruit in _FRUITS if fruit["name"] == "Apple")
    assert next(iter(result.data.values())) == [{"id": apple_id}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["orderedFruits", "orderedFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_order_by(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ {query} {{ waterPercent }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == len(_FRUITS)
    assert result.data[query] == sorted(
        [{"waterPercent": fruit["water_percent"]} for fruit in _FRUITS], key=lambda fruit: fruit["waterPercent"]
    )

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("query", "path"),
    [
        pytest.param("{ orderedFruitsPaginated { id waterPercent } }", ("orderedFruitsPaginated",), id="root-subquery"),
        pytest.param(
            "{ colorsWithOrderedFruits { fruits { id waterPercent } } }",
            ("colorsWithOrderedFruits", "fruits"),
            id="relation",
        ),
        pytest.param(
            "{ colorsWithPaginatedOrderedFruits { fruits(limit: 2) { id waterPercent } } }",
            ("colorsWithPaginatedOrderedFruits", "fruits"),
            id="paginated-relation",
        ),
    ],
)
async def test_query_hook_loaded_column_selected_once(
    query: str,
    path: tuple[str, ...],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that a column loaded by a hook and selected by the query is selected once and read correctly."""
    result = await maybe_async(any_async_query(query))

    assert not result.errors
    assert result.data
    fruits = result.data[path[0]]
    if len(path) > 1:
        fruits = [fruit for color in fruits for fruit in color[path[1]]]
    assert fruits
    water_percents = {fruit["id"]: fruit["water_percent"] for fruit in _FRUITS}
    assert all(fruit["waterPercent"] == water_percents[fruit["id"]] for fruit in fruits)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count(".water_percent AS ") == 1


@pytest.mark.snapshot
async def test_query_hook_on_type(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query("{ colorsWithFilteredFruits { name fruits { name } } }"))

    assert not result.errors
    assert result.data
    assert {
        color["name"]: [fruit["name"] for fruit in color["fruits"]] for color in result.data["colorsWithFilteredFruits"]
    } == {color["name"]: ["Apple"] if color["name"] == "Red" else [] for color in _COLORS}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["fieldFilteredFruits", "fieldFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_root_field_query_hook_where(
    query: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a root list field's query hook filters the root rows."""
    result = await maybe_async(any_async_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[query] == [{"name": "Apple"}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(("apple", "expected"), [(True, {"name": "Apple"}), (False, None)])
@pytest.mark.snapshot
async def test_root_field_query_hook_where_get_by_id(
    apple: bool,
    expected: dict[str, str] | None,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root get-by-id field's query hook hides the rows it filters out."""
    fruit_id = next(fruit["id"] for fruit in _FRUITS if (fruit["name"] == "Apple") is apple)
    result = await maybe_async(any_async_query(f"{{ fieldFilteredFruit(id: {fruit_id}) {{ name }} }}"))

    assert not result.errors
    assert result.data == {"fieldFilteredFruit": expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_root_field_query_hook_where_root_aggregations(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a root aggregation field's query hook filters both nodes and aggregations."""
    result = await maybe_async(
        any_async_query("{ fieldFilteredFruitAggregations { aggregations { count } nodes { name } } }")
    )

    assert not result.errors
    assert result.data
    assert result.data["fieldFilteredFruitAggregations"] == {"aggregations": {"count": 1}, "nodes": [{"name": "Apple"}]}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_root_field_query_hook_load(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root field's query hook loads its columns on the root model."""
    result = await maybe_async(any_async_query("{ fieldLoadFruits { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["fieldLoadFruits"] == [{"name": fruit["name"]} for fruit in _FRUITS]

    assert query_tracker.query_count == 1
    assert "water_percent" in query_tracker[0].statement_str
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["colorsWithSweetFruits", "colorsWithSweetFruitsPaginated"])
@pytest.mark.snapshot
async def test_query_hook_on_relation_field(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a relation field's `query_hook` applies to the related model, not the parent."""
    result = await maybe_async(any_async_query(f"{{ {query} {{ name fruits {{ name }} }} }}"))

    assert not result.errors
    assert result.data
    sweet_fruits = {
        color["name"]: sorted(
            fruit["name"] for fruit in _FRUITS if fruit["color_id"] == color["id"] and fruit["sweetness"] > 5
        )
        for color in _COLORS
    }
    assert {
        color["name"]: sorted(fruit["name"] for fruit in color["fruits"]) for color in result.data[query]
    } == sweet_fruits

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_on_relation_keeps_parent_page_full(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a relation hook does not drop parents from a page, when none of their related rows match it."""
    result = await maybe_async(any_async_query("{ colorsWithSweetFruitsPaginated(limit: 2) { name fruits { name } } }"))

    assert not result.errors
    assert result.data
    assert result.data["colorsWithSweetFruitsPaginated"] == [
        {"name": "Red", "fruits": [{"name": "Cherry"}]},
        {"name": "Yellow", "fruits": []},
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_on_paginated_relation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a relation hook filters the related rows before their pagination applies."""
    result = await maybe_async(any_async_query("{ colorsWithPaginatedSweetFruits { name fruits(limit: 1) { name } } }"))

    assert not result.errors
    assert result.data
    sweet_fruits = {
        color["name"]: {
            fruit["name"] for fruit in _FRUITS if fruit["color_id"] == color["id"] and fruit["sweetness"] > 5
        }
        for color in _COLORS
    }
    fruits_by_color = {
        color["name"]: [fruit["name"] for fruit in color["fruits"]]
        for color in result.data["colorsWithPaginatedSweetFruits"]
    }
    assert fruits_by_color.keys() == sweet_fruits.keys()
    for name, fruits in fruits_by_color.items():
        assert len(fruits) == min(1, len(sweet_fruits[name]))
        assert set(fruits) <= sweet_fruits[name]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_joining_on_relation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a relation hook adding a join restricts the related rows only."""
    result = await maybe_async(any_async_query("{ colorsWithMultiFarmFruits { name fruits { name } } }"))

    assert not result.errors
    assert result.data
    assert {
        color["name"]: sorted(fruit["name"] for fruit in color["fruits"])
        for color in result.data["colorsWithMultiFarmFruits"]
    } == {color["name"]: ["Apple", "Cherry"] if color["name"] == "Red" else [] for color in _COLORS}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


def _fruits_by_water_percent() -> list[tuple[str, list[str]]]:
    return [
        (
            color["name"],
            [
                fruit["name"]
                for fruit in sorted(_FRUITS, key=lambda fruit: fruit["water_percent"])
                if fruit["color_id"] == color["id"]
            ],
        )
        for color in _COLORS
    ]


@pytest.mark.parametrize(
    "fruits_field",
    [
        pytest.param("fruits { name }", id="hook-only"),
        pytest.param("fruits(orderBy: { sweetness: DESC }) { name sweetness }", id="client-order-by"),
    ],
)
@pytest.mark.snapshot
async def test_query_hook_ordering_on_relation(
    fruits_field: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that the ORDER BY of a hook on a related type orders the related rows, ahead of the client ordering."""
    result = await maybe_async(any_async_query(f"{{ colorsWithOrderedFruits {{ name {fruits_field} }} }}"))

    assert not result.errors
    assert result.data
    assert [
        (color["name"], [fruit["name"] for fruit in color["fruits"]])
        for color in result.data["colorsWithOrderedFruits"]
    ] == _fruits_by_water_percent()

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_ordering_on_paginated_relation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that the ORDER BY of a hook on a related type decides which related rows a page keeps."""
    result = await maybe_async(
        any_async_query("{ colorsWithPaginatedOrderedFruits { name fruits(limit: 2, offset: 1) { name } } }")
    )

    assert not result.errors
    assert result.data
    assert [
        (color["name"], [fruit["name"] for fruit in color["fruits"]])
        for color in result.data["colorsWithPaginatedOrderedFruits"]
    ] == [(name, fruits[1:3]) for name, fruits in _fruits_by_water_percent()]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["colorsWithSweetFruits", "colorsWithSweetFruitsPaginated"])
@pytest.mark.snapshot
async def test_query_hook_on_relation_ignored_by_filter(
    query: str,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a filter on a hooked relation considers the related rows the hook leaves out."""
    result = await maybe_async(
        any_async_query(
            f"{{ {query}(filter: {{ fruits: {{ sweetness: {{ lte: 5 }} }} }}) {{ name fruits {{ name }} }} }}"
        )
    )

    assert not result.errors
    assert result.data
    expected = {
        color["name"]: sorted(
            fruit["name"] for fruit in _FRUITS if fruit["color_id"] == color["id"] and fruit["sweetness"] > 5
        )
        for color in _COLORS
        if any(fruit["color_id"] == color["id"] and fruit["sweetness"] <= 5 for fruit in _FRUITS)
    }
    assert {
        color["name"]: sorted(fruit["name"] for fruit in color["fruits"]) for color in result.data[query]
    } == expected

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_joining_on_relation_ignored_by_filter(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a filter on a relation whose hook adds a join considers the related rows the hook leaves out."""
    result = await maybe_async(
        any_async_query(
            '{ colorsWithMultiFarmFruits(filter: { fruits: { name: { in: ["Apple", "Banana"] } } }) { name fruits { name } } }'
        )
    )

    assert not result.errors
    assert result.data
    assert {
        color["name"]: sorted(fruit["name"] for fruit in color["fruits"])
        for color in result.data["colorsWithMultiFarmFruits"]
    } == {"Red": ["Apple", "Cherry"], "Yellow": []}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_order_by_aggregation_of_relation_with_ordering_hook(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test ordering by an aggregate of a to-one relation whose query hook orders its rows."""
    result = await maybe_async(
        any_async_query(
            """
            {
                fruitsWithOrderedColorPaginated(orderBy: { color: { fruitsAggregate: { count: DESC } } }, limit: 3) {
                    id
                    color { id fruitsAggregate { count } }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    color_of = {fruit["id"]: fruit["color_id"] for fruit in _FRUITS}
    fruit_counts = {color_id: list(color_of.values()).count(color_id) for color_id in color_of.values()}
    fruits = result.data["fruitsWithOrderedColorPaginated"]
    for fruit in fruits:
        assert fruit["color"] == {
            "id": color_of[fruit["id"]],
            "fruitsAggregate": {"count": fruit_counts[color_of[fruit["id"]]]},
        }
    assert [fruit["color"]["fruitsAggregate"]["count"] for fruit in fruits] == sorted(
        (fruit_counts[color_id] for color_id in color_of.values()), reverse=True
    )[:3]
    assert query_tracker.query_count == 1


async def test_order_by_relation_with_ordering_hook(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test ordering by a column of a to-one relation whose query hook orders its rows."""
    result = await maybe_async(
        any_async_query("{ fruitsWithOrderedColor(orderBy: { color: { name: DESC } }) { id color { id name } } }")
    )
    assert not result.errors
    assert result.data
    color_names = {color["id"]: color["name"] for color in _COLORS}
    fruits = result.data["fruitsWithOrderedColor"]
    assert sorted(fruit["id"] for fruit in fruits) == sorted(fruit["id"] for fruit in _FRUITS)
    for fruit in fruits:
        color_id = next(raw["color_id"] for raw in _FRUITS if raw["id"] == fruit["id"])
        assert fruit["color"] == {"id": color_id, "name": color_names[color_id]}
    names = [fruit["color"]["name"] for fruit in fruits]
    assert names == sorted(names, reverse=True)
    assert query_tracker.query_count == 1


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "colorNameOrderedFruits(orderBy: [{ sweetness: ASC }])",
            [
                "Lemon",
                "Banana",
                "Quince",
                "Apple",
                "Cherry",
                "Watermelon",
                "Pears",
                "Orange",
                "clementine",
                "Cantaloupe",
                "Strawberry",
            ],
            id="plain",
        ),
        pytest.param(
            "colorNameOrderedFruitsPaginated(orderBy: [{ sweetness: ASC }], limit: 3, offset: 2)",
            ["Quince", "Apple", "Cherry"],
            id="paginated",
        ),
        pytest.param(
            "colorNameOrderedFruits(distinctOn: [colorId], orderBy: [{ sweetness: ASC }])",
            ["Lemon", "Apple", "Watermelon", "Orange", "Cantaloupe"],
            id="distinct-on",
        ),
        pytest.param(
            "colorNameOrderedFruitsPaginated(distinctOn: [colorId], orderBy: [{ sweetness: ASC }], limit: 2, offset: 1)",
            ["Apple", "Watermelon"],
            id="distinct-on-paginated",
        ),
    ],
)
@pytest.mark.snapshot
async def test_query_hook_order_by_joined_alias(
    query: str,
    expected: list[str],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root query hook ordering by an alias it joins orders by that joined alias."""
    result = await maybe_async(any_async_query(f"{{ {query} {{ name }} }}"))
    assert not result.errors
    assert result.data

    assert [fruit["name"] for fruit in next(iter(result.data.values()))] == expected
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param(
            "orderBy: [{ sweetness: DESC }]",
            {
                "Red": ["Cherry", "Apple"],
                "Yellow": ["Quince", "Banana", "Lemon"],
                "Orange": ["clementine", "Orange"],
                "Green": ["Strawberry", "Cantaloupe"],
                "Pink": ["Pears", "Watermelon"],
            },
            id="order-by",
        ),
        pytest.param(
            "distinctOn: [colorId], orderBy: [{ sweetness: DESC }]",
            {
                "Red": ["Cherry"],
                "Yellow": ["Quince"],
                "Orange": ["clementine"],
                "Green": ["Strawberry"],
                "Pink": ["Pears"],
            },
            id="distinct-on",
        ),
    ],
)
@pytest.mark.snapshot
async def test_nested_query_hook_order_by_joined_alias(
    arguments: str,
    expected: dict[str, list[str]],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a relation query hook ordering by an alias it joins orders by that joined alias."""
    result = await maybe_async(
        any_async_query(f"{{ colorsWithColorNameOrderedFruits {{ name fruits({arguments}) {{ name }} }} }}")
    )
    assert not result.errors
    assert result.data

    fruits = {
        color["name"]: [fruit["name"] for fruit in color["fruits"]]
        for color in result.data["colorsWithColorNameOrderedFruits"]
    }
    assert fruits == expected
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
