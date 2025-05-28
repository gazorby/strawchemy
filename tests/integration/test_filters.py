from __future__ import annotations

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData
from .utils import to_graphql_representation

pytestmark = [pytest.mark.integration]


@pytest.mark.snapshot
async def test_no_filtering(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query("{ fruits { id } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["fruits"]) == len(raw_fruits)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_eq(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        {
            fruits(filter: { name: { eq: "Apple" } }) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["fruits"]) == 1
    assert result.data["fruits"][0] == {
        "id": next(fruit["id"] for fruit in raw_fruits if fruit["name"] == "Apple"),
        "name": "Apple",
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_neq(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { name: { neq: "Apple" } }) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["fruits"]) == len(raw_fruits) - 1

    assert result.data["fruits"] == [
        {"id": fruit["id"], "name": fruit["name"]} for fruit in raw_fruits if fruit["name"] != "Apple"
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_isnull(
    any_query: AnyQueryExecutor,
    raw_users: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            users(filter: { bio: { isNull: true } }) {
                id
                bio
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["users"]) == len(raw_users) - 1
    assert result.data["users"] == [{"id": user["id"], "bio": user["bio"]} for user in raw_users if user["bio"] is None]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for in and nin filters
@pytest.mark.snapshot
async def test_in(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { in: [ 1, 9 ] } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] in {1, 9}]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_nin(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { nin: [ 1, 9 ] } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] not in {1, 9}]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_gt(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { gt: 10 } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] > 10]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_gte(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { gte: 9 } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] >= 9]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_lt(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { lt: 1 } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] < 1]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_lte(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: { sweetness: { lte: 1 } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] <= 1]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for string-specific filters
@pytest.mark.parametrize(
    ("filter_name", "value", "expected_ids"),
    [
        pytest.param("like", "%Appl%", [0], id="like"),
        pytest.param("nlike", "%Apple%", list(range(1, 11)), id="nlike"),
        pytest.param("ilike", "%appl%", [0], id="ilike"),
        pytest.param("nilike", "%appl%", list(range(1, 11)), id="nilike"),
        pytest.param("startswith", "Appl", [0], id="startswith"),
        pytest.param("endswith", "pple", [0], id="endswith"),
        pytest.param("contains", "Water", [9], id="contains"),
        pytest.param("istartswith", "appl", [0], id="istartswith"),
        pytest.param("iendswith", "PPLE", [0], id="iendswith"),
        pytest.param("icontains", "water", [9], id="icontains"),
        pytest.param("regexp", "^c.*", [6], id="regexp"),
        pytest.param("iregexp", "^c.*", [1, 6, 8], id="iregexp"),
        pytest.param("nregexp", "^c.*", [0, 1, 2, 3, 4, 5, 7, 8, 9, 10], id="nregexp"),
        pytest.param("inregexp", "^c.*", [0, 2, 3, 4, 5, 7, 9, 10], id="inregexp"),
    ],
)
@pytest.mark.snapshot
async def test_string_filters(
    filter_name: str,
    value: str,
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = f"""
        {{
            fruits(filter: {{ name: {{ {filter_name}: {to_graphql_representation(value, "input")} }} }}) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["fruits"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["fruits"][i]["id"] == raw_fruits[expected_id]["id"]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Tests for logical operators
@pytest.mark.snapshot
async def test_and(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: {
                _and: [
                    { sweetness: { gt: 8 } },
                    { name: { contains: "erry" } }
                ]
            }) {
                id
                name
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] > 8 and "erry" in fruit["name"]]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_or(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: {
                _or: [
                    { sweetness: { gt: 8 } },
                    { name: { contains: "erry" } }
                ]
            }) {
                id
                name
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    expected = [fruit for fruit in raw_fruits if fruit["sweetness"] > 8 or "erry" in fruit["name"]]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_not(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:  # sourcery skip: de-morgan
    query = """
        {
            fruits(filter: { _not: { sweetness: { lt: 10 } } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    expected = [fruit for fruit in raw_fruits if not fruit["sweetness"] < 10]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


# Test complex nested logical operators
@pytest.mark.snapshot
async def test_complex_logical_operators(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruits(filter: {
                _or: [
                    {
                        _and: [
                            { sweetness: { gt: 0 } },
                            { name: { contains: "erry" } }
                        ]
                    },
                    {
                        _and: [
                            { waterPercent: { gt: 0.8 } }
                            { sweetness: { lt: 6 } }
                        ]
                    },
                ]
            }) {
                id
                sweetness
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    expected = [
        fruit
        for fruit in raw_fruits
        if (fruit["sweetness"] > 0 and "erry" in fruit["name"])
        or (fruit["water_percent"] > 0.8 and fruit["sweetness"] < 6)
    ]
    assert len(result.data["fruits"]) == len(expected)
    assert {result.data["fruits"][i]["id"] for i in range(len(expected))} == {fruit["id"] for fruit in expected}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_filter_on_paginated_query(
    any_query: AnyQueryExecutor,
    raw_fruits: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            fruitsPaginatedDefaultLimit1(filter: { _not: { sweetness: { gt: 11 } } }) {
                id
                sweetness
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    expected = [raw_fruits[0]]
    assert len(result.data["fruitsPaginatedDefaultLimit1"]) == len(expected)
    assert {result.data["fruitsPaginatedDefaultLimit1"][i]["id"] for i in range(len(expected))} == {
        fruit["id"] for fruit in expected
    }

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
