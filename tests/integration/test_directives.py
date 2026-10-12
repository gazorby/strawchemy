from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Orange"}]
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
    @strawchemy.type(Fruit, include=["id", "name", "sweetness"])
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"])
    class ColorType: ...

    @strawchemy.type(Color, include=["id", "fruits"], paginate=["fruits"])
    class ColorTypeWithPagination: ...

    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()
        colors_paginated: list[ColorTypeWithPagination] = strawchemy.field(pagination=True)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


async def _data(
    any_async_query: AnyQueryExecutor, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data
    return result.data


_EXCLUDED_FRUITS = [
    pytest.param("fruits @skip(if: true) { id }", {}, id="field-skip"),
    pytest.param("fruits @include(if: false) { id }", {}, id="field-include"),
    pytest.param("fruits @skip(if: $flag) { id }", {"flag": True}, id="field-skip-variable"),
    pytest.param("fruits @include(if: $flag) { id }", {"flag": False}, id="field-include-variable"),
    pytest.param("...ColorFruits @skip(if: true)", {}, id="fragment-spread-skip"),
    pytest.param("...ColorFruits @include(if: $flag)", {"flag": False}, id="fragment-spread-include-variable"),
    pytest.param("... on ColorType @skip(if: true) { fruits { id } }", {}, id="inline-fragment-skip"),
    pytest.param("... @include(if: $flag) { fruits { id } }", {"flag": False}, id="untyped-inline-fragment-include"),
    pytest.param("fruits @skip(if: false) @include(if: false) { id }", {}, id="skip-false-include-false"),
]


def _colors_query(selection: str) -> str:
    variables = "($flag: Boolean! = true)" if "$flag" in selection else ""
    fragment = "fragment ColorFruits on ColorType { fruits { id } }" if "...ColorFruits" in selection else ""
    return f"query {variables} {{ colors {{ id {selection} }} }} {fragment}"


@pytest.mark.parametrize(("selection", "variables"), _EXCLUDED_FRUITS)
async def test_excluded_relation_is_not_joined(
    selection: str,
    variables: dict[str, Any],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that a relation excluded by @skip or @include is left out of the query."""
    data = await _data(any_async_query, _colors_query(selection), variables)
    assert query_tracker.query_count == 1
    assert "JOIN" not in query_tracker[0].statement_formatted
    assert sorted(data["colors"], key=lambda color: color["id"]) == [{"id": color["id"]} for color in _COLORS]


@pytest.mark.parametrize(
    ("selection", "variables"),
    [
        pytest.param("fruits @skip(if: false) { id }", {}, id="field-skip"),
        pytest.param("fruits @include(if: $flag) { id }", {"flag": True}, id="field-include-variable"),
        pytest.param("fruits @include(if: $flag) { id }", {}, id="field-include-variable-default"),
        pytest.param("...ColorFruits @include(if: true)", {}, id="fragment-spread-include"),
        pytest.param("... on ColorType @skip(if: false) { fruits { id } }", {}, id="inline-fragment-skip"),
        pytest.param("... { fruits { id } }", {}, id="untyped-inline-fragment"),
    ],
)
async def test_included_relation_is_joined(
    selection: str, variables: dict[str, Any], any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a relation kept by @skip or @include is loaded."""
    data = await _data(any_async_query, _colors_query(selection), variables)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    assert all("fruits" in color for color in data["colors"])


@pytest.mark.parametrize(
    ("directive", "variables"),
    [
        pytest.param("@skip(if: true)", {}, id="skip"),
        pytest.param("@include(if: $flag)", {"flag": False}, id="include-variable"),
    ],
)
async def test_excluded_column_is_not_selected(
    directive: str,
    variables: dict[str, Any],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that a column excluded by @skip or @include is left out of the query."""
    data = await _data(any_async_query, _colors_query(f"name {directive}"), variables)
    assert query_tracker.query_count == 1
    assert "name" not in query_tracker[0].statement_formatted
    assert sorted(data["colors"], key=lambda color: color["id"]) == [{"id": color["id"]} for color in _COLORS]


async def test_excluded_alias_with_other_arguments_adds_no_join(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that a skipped alias of a relation, with arguments of its own, adds no join next to the kept alias."""
    data = await _data(
        any_async_query, "{ colorsPaginated { id a: fruits { id } b: fruits(limit: null) @skip(if: true) { id } } }"
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in data["colorsPaginated"]:
        assert set(color) == {"id", "a"}
        assert color["a"] == [
            {"id": fruit["id"]}
            for fruit in sorted(_FRUITS, key=lambda fruit: fruit["id"])
            if fruit["color_id"] == color["id"]
        ]


async def test_excluded_identity_column(any_async_query: AnyQueryExecutor, query_tracker: QueryTracker) -> None:
    """Test that skipping the primary key still loads the relations of each row."""
    data = await _data(any_async_query, "{ colors { id @skip(if: true) name fruits { name } } }")
    assert query_tracker.query_count == 1
    expected = [
        {
            "name": color["name"],
            "fruits": sorted(fruit["name"] for fruit in _FRUITS if fruit["color_id"] == color["id"]),
        }
        for color in _COLORS
    ]
    actual = [
        {"name": color["name"], "fruits": sorted(fruit["name"] for fruit in color["fruits"])}
        for color in data["colors"]
    ]
    assert sorted(actual, key=lambda color: color["name"]) == sorted(expected, key=lambda color: color["name"])


async def test_same_response_key_under_different_directives(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
) -> None:
    """Test that a skipped occurrence of a response key leaves only the fields of the kept occurrence."""
    data = await _data(any_async_query, "{ colors { id fruits @skip(if: true) { sweetness } fruits { name } } }")
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    assert "sweetness" not in query_tracker[0].statement_formatted
    for color in data["colors"]:
        assert sorted(color["fruits"], key=lambda fruit: fruit["name"]) == sorted(
            ({"name": fruit["name"]} for fruit in _FRUITS if fruit["color_id"] == color["id"]),
            key=lambda fruit: fruit["name"],
        )
