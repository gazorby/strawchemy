from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.fixtures import QueryTracker
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

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


def _names_by_color(colors: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {color["name"]: sorted(fruit["name"] for fruit in color["fruits"]) for color in colors}


@pytest.mark.snapshot
async def test_to_many_filter_keeps_every_selected_related_row(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a filter on a to-many relation selects parents without restricting the selected relation.

    Regression test for #290: the filter join was reused to load the selection, which only kept the matching rows.
    """
    query = """
        {
            colors(filter: { fruits: { sweetness: { lte: 5 } } }) {
                name
                fruits { name }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert _names_by_color(result.data["colors"]) == {
        "Red": ["Apple", "Cherry"],
        "Yellow": ["Banana", "Lemon", "Quince"],
        "Green": ["Cantaloupe", "Strawberry"],
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_to_many_filter_on_paginated_field_keeps_every_selected_related_row(any_query: AnyQueryExecutor) -> None:
    """Test that a paginated field and a plain one return the same related rows under a to-many filter."""
    query = """
        {
            colorsFilterablePaginated(filter: { fruits: { sweetness: { lte: 5 } } }) {
                name
                fruits { name }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert _names_by_color(result.data["colorsFilterablePaginated"]) == {
        "Red": ["Apple", "Cherry"],
        "Yellow": ["Banana", "Lemon", "Quince"],
        "Green": ["Cantaloupe", "Strawberry"],
    }


@pytest.mark.snapshot
async def test_to_many_filter_paginates_distinct_parents(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a parent matching a to-many filter through several rows takes one slot of the page.

    Regression test for #291: the pagination subquery joined the relation, so LIMIT counted each matching row.
    """
    query = """
        {
            colorsFilterablePaginated(limit: 3, filter: { fruits: { sweetness: { lte: 5 } } }, orderBy: { name: ASC }) {
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert result.data["colorsFilterablePaginated"] == [{"name": "Green"}, {"name": "Red"}, {"name": "Yellow"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_to_many_filter_in_or_branch_keeps_every_selected_related_row(any_query: AnyQueryExecutor) -> None:
    """Test that a to-many filter under ``_or`` selects parents without restricting the selected relation."""
    query = """
        {
            colors(filter: { _or: [{ fruits: { name: { eq: "Apple" } } }, { name: { eq: "Pink" } }] }) {
                name
                fruits { name }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert _names_by_color(result.data["colors"]) == {"Red": ["Apple", "Cherry"], "Pink": ["Pears", "Watermelon"]}


@pytest.mark.snapshot
async def test_to_many_filter_behind_to_one_keeps_every_selected_related_row(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a to-many filter reached through a to-one relation leaves the selected relations whole."""
    query = """
        {
            fruits(filter: { color: { fruits: { name: { eq: "Apple" } } } }) {
                name
                color { name fruits { name } }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert sorted(
        (fruit["name"], fruit["color"]["name"], sorted(sibling["name"] for sibling in fruit["color"]["fruits"]))
        for fruit in result.data["fruits"]
    ) == [("Apple", "Red", ["Apple", "Cherry"]), ("Cherry", "Red", ["Apple", "Cherry"])]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_to_many_filter_and_column_filter(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a column filter next to a to-many filter restricts the parents outside of the EXISTS subquery."""
    query = """
        {
            colors(filter: { name: { neq: "Red" }, fruits: { sweetness: { lte: 5 } } }) {
                name
                fruits { name }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert _names_by_color(result.data["colors"]) == {
        "Yellow": ["Banana", "Lemon", "Quince"],
        "Green": ["Cantaloupe", "Strawberry"],
    }
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_to_many_filter_and_to_one_filter(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a to-one filter next to a to-many filter restricts the parents through a join."""
    query = """
        {
            users(filter: { group: { name: { eq: "Group 1" } }, departments: { name: { eq: "IT" } } }) {
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert result.data["users"] == [{"name": "Alice"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "arguments"),
    [
        pytest.param("users", "", id="plain"),
        pytest.param("usersPaginated", "", id="paginated"),
        pytest.param("users", ", distinctOn: [name]", id="distinct-on"),
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ departments: { name: { isNull: true } } }", [], id="to-many-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { name: { isNull: true } } }', [], id="column-and-to-many-null"
        ),
        pytest.param("{ group: { name: { isNull: true } } }", [], id="to-one-null"),
        pytest.param('{ name: { neq: "Zed" }, group: { name: { isNull: true } } }', [], id="column-and-to-one-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { _or: [{ name: { isNull: true } }, { name: { eq: "IT" } }] } }',
            ["Alice", "Charlie"],
            id="column-and-to-many-or-null",
        ),
        pytest.param(
            '{ group: { name: { isNull: true } }, departments: { name: { eq: "IT" } } }',
            [],
            id="to-one-null-and-to-many",
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { isNull: true } } }] }', ["Bob"], id="or-to-one-null"
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { departments: { name: { isNull: true } } }] }',
            ["Bob"],
            id="or-to-many-null",
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { eq: "Group 1" } } }] }',
            ["Alice", "Bob"],
            id="or-to-one",
        ),
        pytest.param(
            "{ _not: { group: { name: { isNull: true } } } }",
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-to-one-null",
        ),
        pytest.param(
            '{ name: { neq: "Zed" }, _not: { group: { name: { isNull: true } } } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="column-and-not-to-one-null",
        ),
        pytest.param('{ _not: { group: { name: { eq: "Group 1" } } } }', ["Bob", "Charlie", "Tango"], id="not-to-one"),
        pytest.param(
            '{ name: { neq: "Zed" }, _not: { group: { name: { eq: "Group 1" } } } }',
            ["Bob", "Charlie", "Tango"],
            id="column-and-not-to-one",
        ),
        pytest.param("{ departments: { users: { group: { name: { isNull: true } } } } }", [], id="nested-to-one-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { users: { group: { name: { isNull: true } } } } }',
            [],
            id="column-and-nested-to-one-null",
        ),
        pytest.param(
            '{ departments: { name: { neq: "Zed" }, users: { group: { name: { isNull: true } } } } }',
            [],
            id="nested-column-and-to-one-null",
        ),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } }, "
            "group: { name: { isNull: true } } }",
            [],
            id="aggregation-and-to-one-null",
        ),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } }, "
            "departments: { name: { isNull: true } } }",
            [],
            id="aggregation-and-to-many-null",
        ),
        pytest.param('{ group: { _not: { name: { eq: "Group 1" } } } }', [], id="to-one-not"),
        pytest.param('{ departments: { _not: { name: { eq: "IT" } } } }', ["Bob", "Charlie"], id="to-many-not"),
        pytest.param(
            '{ departments: { _or: [{ name: { eq: "Sales" } }, { _not: { name: { isNull: false } } }] } }',
            ["Bob"],
            id="to-many-or-not",
        ),
        pytest.param(
            "{ departments: { usersAggregate: { count: { arguments: [id], predicate: { lt: 2 } } } } }",
            ["Bob", "Charlie"],
            id="to-many-aggregation",
        ),
        pytest.param(
            "{ group: { topicsAggregate: { count: { arguments: [id], predicate: { eq: 0 } } } } }",
            [],
            id="to-one-aggregation",
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, '
            "{ group: { topicsAggregate: { count: { arguments: [id], predicate: { eq: 0 } } } } }] }",
            ["Bob"],
            id="or-to-one-aggregation",
        ),
        pytest.param(
            '{ _or: [{ group: { name: { eq: "Group 1" } } }, { departments: { name: { eq: "Sales" } } }] }',
            ["Alice", "Bob"],
            id="or-to-one-and-to-many",
        ),
        pytest.param(
            "{ _or: [{ departmentsAggregate: { count: { arguments: [id], predicate: { eq: 0 } } } }, "
            "{ group: { name: { isNull: true } } }] }",
            ["Tango"],
            id="or-aggregation-and-to-one-null",
        ),
        pytest.param(
            "{ _or: [{ departmentsAggregate: { count: { arguments: [id], predicate: { eq: 0 } } } }, "
            '{ group: { name: { eq: "Group 1" } } }] }',
            ["Alice", "Tango"],
            id="or-aggregation-and-to-one",
        ),
    ],
)
async def test_relation_filter_ignores_siblings(
    field: str, arguments: str, dto_filter: str, names: list[str], any_query: AnyQueryExecutor
) -> None:
    """Test that a relation filter only matches rows having a matching related row, whatever its sibling filters."""
    result = await maybe_async(any_query(f"{{ {field}(filter: {dto_filter}{arguments}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data[field]) == names


@pytest.mark.snapshot
async def test_not_isnull(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ users(filter: { _not: { bio: { isNull: true } } }) { name } }"))
    assert not result.errors
    assert result.data

    assert result.data["users"] == [{"name": "Tango"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ _not: { bio: { isNull: false } } }", ["Alice", "Bob", "Charlie"], id="not-isnull-false"),
        pytest.param('{ _not: { bio: { eq: "Tango\'s bio" } } }', ["Alice", "Bob", "Charlie"], id="not-eq"),
        pytest.param(
            '{ _not: { bio: { isNull: true, eq: "Tango\'s bio" } } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-isnull-and-eq",
        ),
        pytest.param(
            '{ _not: { _or: [{ bio: { isNull: true } }, { name: { eq: "Bob" } }] } }', ["Tango"], id="not-or-isnull"
        ),
        pytest.param("{ _not: { _not: { bio: { isNull: true } } } }", ["Alice", "Bob", "Charlie"], id="not-not-isnull"),
        pytest.param("{ _not: { bio: { eq: null } } }", ["Tango"], id="not-eq-null"),
        pytest.param("{ _not: { bio: { neq: null } } }", ["Alice", "Bob", "Charlie"], id="not-neq-null"),
    ],
)
async def test_not_isnull_column(dto_filter: str, names: list[str], any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    ("raw_groups", "raw_users", "raw_departments"),
    [
        pytest.param(
            [
                {"id": 1, "name": "Group 1"},
                {"id": 2, "name": None},
                *({"id": i, "name": f"Group {i}"} for i in (3, 4, 5)),
            ],
            [
                {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
                {"id": 2, "name": "Bob", "group_id": 2, "bio": None},
                {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
                {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
            ],
            [{"id": 1, "name": "IT"}, {"id": 2, "name": None}, {"id": 3, "name": "Platform"}],
            id="null-names",
        )
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ group: { name: { isNull: true } } }", ["Bob"], id="to-one-isnull"),
        pytest.param(
            "{ _not: { group: { name: { isNull: true } } } }", ["Alice", "Charlie", "Tango"], id="not-to-one-isnull"
        ),
        pytest.param(
            "{ _not: { group: { name: { isNull: false } } } }",
            ["Bob", "Charlie", "Tango"],
            id="not-to-one-isnull-false",
        ),
        pytest.param("{ group: { _not: { name: { isNull: true } } } }", ["Alice"], id="to-one-not-isnull"),
        pytest.param("{ departments: { name: { isNull: true } } }", ["Bob"], id="to-many-isnull"),
        pytest.param(
            "{ _not: { departments: { name: { isNull: true } } } }",
            ["Alice", "Charlie", "Tango"],
            id="not-to-many-isnull",
        ),
        pytest.param(
            "{ departments: { _not: { name: { isNull: true } } } }", ["Alice", "Charlie"], id="to-many-not-isnull"
        ),
    ],
)
async def test_not_isnull_relation(
    dto_filter: str,
    names: list[str],
    any_query: AnyQueryExecutor,
    raw_groups: RawRecordData,  # noqa: ARG001
    raw_users: RawRecordData,  # noqa: ARG001
    raw_departments: RawRecordData,  # noqa: ARG001
) -> None:
    """Test ``isNull`` on the columns of NULL-named related rows, directly and under ``_not``."""
    result = await maybe_async(any_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names
