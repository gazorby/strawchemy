from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from tests.integration.fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_columns_hook(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ description }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"description": f"The {fruit['name']} color id is {fruit['color_id']}"} for fruit in raw_fruits
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_relationships_with_columns(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ prettyColor }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[fruits_query] == [
        {"prettyColor": f"Color is {next(color['name'] for color in raw_colors if color['id'] == fruit['color_id'])}"}
        for fruit in raw_fruits
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
@pytest.mark.snapshot
async def test_load_relationships_no_columns(
    fruits_query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
    raw_farms: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ prettyFarms }} }}"))

    assert not result.errors
    assert result.data
    farm_names = [
        ", ".join(farm["name"] for farm in raw_farms if farm["fruit_id"] == fruit["id"]) for fruit in raw_fruits
    ]
    assert result.data[fruits_query] == [{"prettyFarms": f"Farms are: {name}"} for name in farm_names]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsWithFilteredFruits", "colorsWithFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_nested(
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    raw_farms: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ farms }} }}"))

    assert not result.errors
    assert result.data

    # The query asks for no ordering, so the farms of a fruit come back in a dialect-dependent order.
    farm_names = [
        sorted(
            farm["name"]
            for fruit in raw_fruits
            if fruit["color_id"] == color["id"]
            for farm in raw_farms
            if farm["fruit_id"] == fruit["id"]
        )
        for color in raw_colors
    ]
    assert [
        sorted(entry["farms"].removeprefix("Farms are: ").split(", ")) for entry in result.data[query]
    ] == farm_names

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("query", ["colorsHooks", "colorsHooksPaginated"])
@pytest.mark.snapshot
async def test_load_relationships_on_nested_field(
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ id fruits {{ prettyColor }} }} }}"))

    assert not result.errors
    assert result.data
    assert result.data[query] == [
        {
            "id": color["id"],
            "fruits": [
                {"prettyColor": f"Color is {color['name']}"}
                for _ in range(len([fruit for fruit in raw_fruits if fruit["color_id"] == color["id"]]))
            ],
        }
        for color in raw_colors
    ]

    query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize("fruits_query", ["fruitsHooks", "fruitsPaginatedHooks"])
async def test_empty_query_hook(fruits_query: str, any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query(f"{{ {fruits_query} {{ emptyQueryHook }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[fruits_query]) == len(raw_fruits)
    assert result.data[fruits_query] == [{"emptyQueryHook": "success"} for _ in range(len(raw_fruits))]


@pytest.mark.parametrize("query", ["filteredFruits", "filteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_where(
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ name }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == 1
    assert result.data[query] == [{"name": "Apple"}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["orderedFruits", "orderedFruitsPaginated"])
@pytest.mark.snapshot
async def test_custom_query_hook_order_by(
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    raw_fruits: RawRecordData,
) -> None:
    result = await maybe_async(any_query(f"{{ {query} {{ waterPercent }} }}"))

    assert not result.errors
    assert result.data
    assert len(result.data[query]) == len(raw_fruits)
    assert result.data[query] == sorted(
        [{"waterPercent": fruit["water_percent"]} for fruit in raw_fruits], key=lambda fruit: fruit["waterPercent"]
    )

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_query_hook_on_type(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ colorsWithFilteredFruits { fruits { name } } }"))

    assert not result.errors
    assert result.data
    assert len(result.data["colorsWithFilteredFruits"]) == 1
    assert result.data["colorsWithFilteredFruits"] == [{"fruits": [{"name": "Apple"}]}]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("query", ["fieldFilteredFruits", "fieldFilteredFruitsPaginated"])
@pytest.mark.snapshot
async def test_root_field_query_hook_where(
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a root list field's query hook filters the root rows."""
    result = await maybe_async(any_query(f"{{ {query} {{ name }} }}"))

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
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root get-by-id field's query hook hides the rows it filters out."""
    fruit_id = next(fruit["id"] for fruit in raw_fruits if (fruit["name"] == "Apple") is apple)
    result = await maybe_async(any_query(f"{{ fieldFilteredFruit(id: {fruit_id}) {{ name }} }}"))

    assert not result.errors
    assert result.data == {"fieldFilteredFruit": expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_root_field_query_hook_where_root_aggregations(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a root aggregation field's query hook filters both nodes and aggregations."""
    result = await maybe_async(
        any_query("{ fieldFilteredFruitAggregations { aggregations { count } nodes { name } } }")
    )

    assert not result.errors
    assert result.data
    assert result.data["fieldFilteredFruitAggregations"] == {"aggregations": {"count": 1}, "nodes": [{"name": "Apple"}]}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_root_field_query_hook_load(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a root field's query hook loads its columns on the root model."""
    result = await maybe_async(any_query("{ fieldLoadFruits { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["fieldLoadFruits"] == [{"name": fruit["name"]} for fruit in raw_fruits]

    assert query_tracker.query_count == 1
    assert "water_percent" in query_tracker[0].statement_str
    assert query_tracker[0].statement_formatted == sql_snapshot
