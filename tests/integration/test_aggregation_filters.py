from __future__ import annotations

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

pytestmark = [pytest.mark.integration]


@pytest.mark.parametrize(
    ("predicate", "value", "expected_indices"),
    [
        pytest.param("eq", 2, [0, 2, 3, 4], id="eq-match"),
        pytest.param("neq", 0, [0, 1, 2, 3, 4], id="neq-match"),
        pytest.param("gt", 1, [0, 1, 2, 3, 4], id="gt-match"),
        pytest.param("gte", 2, [0, 1, 2, 3, 4], id="gte-match"),
        pytest.param("lt", 3, [0, 2, 3, 4], id="lt-match"),
        pytest.param("lte", 2, [0, 2, 3, 4], id="lte-match"),
        pytest.param("in", [1, 2, 3], [0, 1, 2, 3, 4], id="in-match"),
        pytest.param("nin", [0, 3, 4], [0, 2, 3, 4], id="nin-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter(
    predicate: str,
    value: int | list[int],
    expected_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation."""
    # Prepare the value for GraphQL query
    value_str = f"[{', '.join(str(v) for v in value)}]" if isinstance(value, list) else str(value)

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    count: {{
                        arguments: [id]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_indices)

    # Get the container IDs from the result
    result_container_ids = {container["id"] for container in result.data["colors"]}

    # Get the expected container IDs
    expected_container_ids = {raw_colors[idx]["id"] for idx in expected_indices}

    # Assert that the result contains exactly the expected container IDs
    assert result_container_ids == expected_container_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("name", "eq", "Apple", [0], id="eq-match"),
        pytest.param("name", "like", "%pp%", [0], id="like-match"),
        pytest.param("name", "ilike", "%APP%", [0], id="ilike-match"),
        pytest.param("name", "startswith", "App", [0], id="startswith-match"),
        pytest.param("name", "contains", "ppl", [0], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_min_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_color_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by minString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    minString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {raw_colors[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("name", "eq", "Cherry", [0], id="eq-match"),
        pytest.param("name", "like", "%err%", [0, 3], id="like-match"),
        pytest.param("name", "ilike", "%ERR%", [0, 3], id="ilike-match"),
        pytest.param("name", "startswith", "Che", [0], id="startswith-match"),
        pytest.param("name", "contains", "err", [0, 3], id="contains-match"),
    ],
)
@pytest.mark.snapshot
async def test_max_string_aggregation_filter(
    field: str,
    predicate: str,
    value: str,
    expected_color_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by maxString aggregation."""
    value_str = f'"{value}"'

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    maxString: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {raw_colors[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("sweetness", "eq", 6, [1], id="int-eq-match"),
        pytest.param("sweetness", "gt", 8, [0, 2, 4], id="int-gt-match"),
        pytest.param("waterPercent", "eq", 1.77, [0], id="float-eq-match"),
        pytest.param("waterPercent", "gt", 1.7, [0, 1, 2], id="float-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_sum_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_color_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by sum aggregation."""
    value_str = str(value)

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    sum: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value_str} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {raw_colors[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "predicate", "value", "expected_color_indices"),
    [
        pytest.param("sweetness", "eq", 6.5, [0], id="int-avg-eq-match"),
        pytest.param("sweetness", "gt", 7.0, [2, 4], id="int-avg-gt-match"),
        pytest.param("waterPercent", "eq", 0.885, [0], id="float-avg-eq-match"),
        pytest.param("waterPercent", "gt", 0.85, [0, 2], id="float-avg-gt-match"),
    ],
)
@pytest.mark.snapshot
async def test_avg_aggregation_filter(
    field: str,
    predicate: str,
    value: float,
    expected_color_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by avg aggregation."""
    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    avg: {{
                        arguments: [{field}]
                        predicate: {{ {predicate}: {value} }}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {raw_colors[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("distinct", "expected_count", "expected_color_indices"),
    [
        pytest.param(True, 2, [0, 2, 3, 4], id="distinct-match"),
        pytest.param(False, 2, [0, 2, 3, 4], id="non-distinct-match"),
        pytest.param(None, 2, [0, 2, 3, 4], id="default-match"),
    ],
)
@pytest.mark.snapshot
async def test_count_aggregation_filter_with_distinct(
    distinct: bool | None,
    expected_count: int,
    expected_color_indices: list[int],
    any_query: AnyQueryExecutor,
    raw_colors: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test filtering by count aggregation with distinct option."""
    distinct_str = f"distinct: {to_graphql_representation(distinct, 'input')}" if distinct is not None else ""

    query = f"""
        {{
            colors(filter: {{
                fruitsAggregate: {{
                    count: {{
                        arguments: [name]
                        predicate: {{ eq: {expected_count} }}
                        {distinct_str}
                    }}
                }}
            }}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert len(result.data["colors"]) == len(expected_color_indices)

    # Get the color IDs from the result
    result_color_ids = {color["id"] for color in result.data["colors"]}

    # Get the expected color IDs
    expected_color_ids = {raw_colors[idx]["id"] for idx in expected_color_indices}

    # Assert that the result contains exactly the expected color IDs
    assert result_color_ids == expected_color_ids

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
