from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from tests.integration.fixtures import QueryTracker
    from tests.integration.typing import RawRecordData
    from tests.typing import AnyQueryExecutor


@pytest.mark.snapshot
async def test_custom_apply_filter_sweeter_than(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    threshold = 5
    expected_ids = {fruit["id"] for fruit in raw_fruits if fruit["sweetness"] >= threshold}
    query = f"""
        {{
            fruitsFineGrained(filter: {{ sweeterThan: {threshold} }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_custom_apply_filter_in_strategy(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    threshold = 5
    expected_ids = {fruit["id"] for fruit in raw_fruits if fruit["sweetness"] >= threshold}
    query = f"""
        {{
            fruitsFineGrained(filter: {{ sweeterThanIn: {threshold} }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_restricted_operator_only_selected_exposed(any_query: AnyQueryExecutor) -> None:
    # `contains` is not in the selected ops {eq, like} -> GraphQL validation error.
    query = """
        {
            fruitsFineGrained(filter: { name: { contains: "x" } }) {
                id
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert result.errors


async def test_custom_apply_filter_under_or(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    threshold = 8
    target_name = raw_fruits[0]["name"]
    expected_ids = {
        fruit["id"] for fruit in raw_fruits if fruit["sweetness"] >= threshold or fruit["name"] == target_name
    }
    query = f"""
        {{
            fruitsFineGrained(
                filter: {{
                    _or: [
                        {{ sweeterThan: {threshold} }}
                        {{ name: {{ eq: "{target_name}" }} }}
                    ]
                }}
            ) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data is not None
    assert {row["id"] for row in result.data["fruitsFineGrained"]} == expected_ids
