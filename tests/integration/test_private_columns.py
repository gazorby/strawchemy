from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.utils import to_graphql_representation
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]


@pytest.mark.snapshot
async def test_private_column_is_set(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a private model column is loaded and readable by a resolver when it is not selected."""
    result = await maybe_async(any_query("{ fruitsPrivateName { id upperName } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruitsPrivateName"] == [
        {"id": to_graphql_representation(fruit["id"], "output"), "upperName": fruit["name"].upper()}
        for fruit in raw_fruits
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_private_column_of_to_one_relation_is_set(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a private column of a to-one related type is loaded when only the relation is selected."""
    result = await maybe_async(any_query("{ fruitsPrivateName { id color { id upperName } } }"))

    assert not result.errors
    assert result.data
    colors = {color["id"]: color for color in raw_colors}
    assert result.data["fruitsPrivateName"] == [
        {
            "id": to_graphql_representation(fruit["id"], "output"),
            "color": {
                "id": to_graphql_representation(fruit["color_id"], "output"),
                "upperName": colors[fruit["color_id"]]["name"].upper(),
            },
        }
        for fruit in raw_fruits
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_private_column_of_to_many_relation_is_set(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
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
            "fruits": sorted(fruit["name"].upper() for fruit in raw_fruits if fruit["color_id"] == color["id"]),
        }
        for color in raw_colors
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_returns_private_column(
    any_query: AnyQueryExecutor, raw_colors: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a create mutation result type sets its private columns and those of its relations."""
    color_id = to_graphql_representation(raw_colors[0]["id"], "input")
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
        "color": {"upperName": raw_colors[0]["name"].upper()},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_returns_private_column(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that an update mutation result type sets its private columns."""
    fruit_id = to_graphql_representation(raw_fruits[0]["id"], "input")
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
