from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from tests.integration.fixtures import QueryTracker
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

pytestmark = [pytest.mark.integration]


async def _data(any_query: AnyQueryExecutor, query: str) -> dict[str, Any]:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    return result.data


def _fruits_of(
    raw_fruits: RawRecordData, color_id: int, *, by: str = "id", descending: bool = False
) -> list[dict[str, Any]]:
    fruits = [fruit for fruit in raw_fruits if fruit["color_id"] == color_id]
    return sorted(fruits, key=lambda fruit: fruit[by], reverse=descending)


async def test_aliased_relations_with_different_order_by(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that two aliases of a relation ordered differently are each ordered their own way, in one query."""
    data = await _data(
        any_query,
        """
        {
            colors {
                id
                a: fruits(orderBy: { sweetness: DESC }) { id }
                b: fruits(orderBy: { sweetness: ASC }) { id }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    for color in data["colors"]:
        ascending = [{"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"], by="sweetness")]
        assert color["a"] == ascending[::-1]
        assert color["b"] == ascending


async def test_aliased_relations_with_different_pagination(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that two aliases of a relation paginated differently each get their own page, in one query."""
    data = await _data(
        any_query,
        """
        {
            colorsPaginated(limit: 3, offset: 1) {
                id
                a: fruits(limit: 1) { id }
                b: fruits(limit: 1, offset: 1) { id }
                c: fruits { id }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    assert [color["id"] for color in data["colorsPaginated"]] == [2, 3, 4]
    for color in data["colorsPaginated"]:
        fruits = [{"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"])]
        assert color["a"] == fruits[:1]
        assert color["b"] == fruits[1:2]
        assert color["c"] == fruits


async def test_aliased_relations_with_different_arguments_and_selections(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, raw_colors: RawRecordData
) -> None:
    """Test that aliases with different arguments keep their own selection, sub-relations included."""
    data = await _data(
        any_query,
        """
        {
            colors {
                id
                a: fruits(orderBy: { sweetness: DESC }) { name }
                b: fruits(orderBy: { sweetness: ASC }) { id sweetness color { name } }
            }
        }
        """,
    )
    color_names = {color["id"]: color["name"] for color in raw_colors}
    for color in data["colors"]:
        ascending = _fruits_of(raw_fruits, color["id"], by="sweetness")
        assert color["a"] == [{"name": fruit["name"]} for fruit in reversed(ascending)]
        assert color["b"] == [
            {"id": fruit["id"], "sweetness": fruit["sweetness"], "color": {"name": color_names[color["id"]]}}
            for fruit in ascending
        ]


async def test_aliased_relations_with_and_without_arguments(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData
) -> None:
    """Test that an alias without arguments is unaffected by another alias of the same relation that has some."""
    data = await _data(
        any_query,
        """
        {
            colors {
                id
                a: fruits { id }
                b: fruits(orderBy: { sweetness: DESC }) { id }
            }
        }
        """,
    )
    for color in data["colors"]:
        assert color["a"] == [{"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"])]
        assert color["b"] == [
            {"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"], by="sweetness", descending=True)
        ]


async def test_aliased_relations_nested_in_relation(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that aliases of a relation with different arguments, below another relation, are each ordered."""
    data = await _data(
        any_query,
        """
        {
            fruits {
                id
                colorId
                color {
                    a: fruits(orderBy: { sweetness: DESC }) { id }
                    b: fruits(orderBy: { sweetness: ASC }) { id }
                }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    for fruit in data["fruits"]:
        ascending = [{"id": related["id"]} for related in _fruits_of(raw_fruits, fruit["colorId"], by="sweetness")]
        assert fruit["color"]["a"] == ascending[::-1]
        assert fruit["color"]["b"] == ascending


async def test_aliased_relations_with_same_arguments_share_one_join(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that aliases of a relation with the same arguments share one join and both get the merged selection."""
    data = await _data(
        any_query,
        """
        {
            colors {
                id
                a: fruits(orderBy: { sweetness: DESC }) { id }
                b: fruits(orderBy: { sweetness: DESC }) { id sweetness }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("JOIN") == 1
    for color in data["colors"]:
        descending = _fruits_of(raw_fruits, color["id"], by="sweetness", descending=True)
        assert color["a"] == [{"id": fruit["id"]} for fruit in descending]
        assert color["b"] == [{"id": fruit["id"], "sweetness": fruit["sweetness"]} for fruit in descending]


async def test_aliased_relations_with_computed_values(
    any_query: AnyQueryExecutor, raw_fruits: RawRecordData, raw_farms: RawRecordData
) -> None:
    """Test that computed values under one alias still map to the right objects when another alias has arguments."""
    data = await _data(
        any_query,
        """
        {
            colors {
                id
                a: fruits { id farmsAggregate { count } }
                b: fruits(orderBy: { sweetness: DESC }) { id }
            }
        }
        """,
    )
    farm_counts = Counter(farm["fruit_id"] for farm in raw_farms)
    for color in data["colors"]:
        assert color["a"] == [
            {"id": fruit["id"], "farmsAggregate": {"count": farm_counts[fruit["id"]]}}
            for fruit in _fruits_of(raw_fruits, color["id"])
        ]
        assert color["b"] == [
            {"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"], by="sweetness", descending=True)
        ]


async def test_aliased_relations_with_query_hook(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that a relation query hook applies to every alias of the relation, each keeping its own page."""
    data = await _data(
        any_query,
        """
        {
            colorsWithPaginatedSweetFruits {
                id
                a: fruits(limit: 1) { id }
                b: fruits(limit: 1, offset: 1) { id }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    for color in data["colorsWithPaginatedSweetFruits"]:
        sweet = [{"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color["id"]) if fruit["sweetness"] > 5]
        assert color["a"] == sweet[:1]
        assert color["b"] == sweet[1:2]


async def test_aliased_relations_under_to_one_relation_selected_twice(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that aliases of a to-one relation merge, and the differently-argued relations below each keep theirs."""
    data = await _data(
        any_query,
        """
        {
            fruits {
                colorId
                x: color { a: fruits(orderBy: { sweetness: DESC }) { id } }
                y: color { b: fruits(orderBy: { sweetness: ASC }) { id } }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    for fruit in data["fruits"]:
        ascending = [{"id": related["id"]} for related in _fruits_of(raw_fruits, fruit["colorId"], by="sweetness")]
        assert fruit["x"] == {"a": ascending[::-1]}
        assert fruit["y"] == {"b": ascending}


async def test_mutation_returning_aliased_relations(
    any_query: AnyQueryExecutor, raw_colors: RawRecordData, raw_fruits: RawRecordData
) -> None:
    """Test that a mutation result selecting aliases of a relation with different arguments returns each alias."""
    color_id = raw_colors[0]["id"]
    data = await _data(
        any_query,
        f"""
        mutation {{
            updateColor(data: {{ id: {to_graphql_representation(color_id, "input")}, name: "updated" }}) {{
                name
                a: fruits(orderBy: {{ sweetness: DESC }}) {{ id }}
                b: fruits(orderBy: {{ sweetness: ASC }}) {{ id }}
            }}
        }}
        """,
    )
    ascending = [{"id": fruit["id"]} for fruit in _fruits_of(raw_fruits, color_id, by="sweetness")]
    assert data["updateColor"] == {"name": "updated", "a": ascending[::-1], "b": ascending}


async def test_aliased_relations_with_same_query_hook_apply_it_once(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, raw_fruits: RawRecordData
) -> None:
    """Test that aliases of a hooked relation sharing one node run the relation's query hook only once."""
    data = await _data(
        any_query,
        """
        {
            colorsWithSweetFruits {
                id
                a: fruits { id }
                b: fruits { name }
            }
        }
        """,
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted.count("> ") == 1
    for color in data["colorsWithSweetFruits"]:
        sweet = [fruit for fruit in _fruits_of(raw_fruits, color["id"]) if fruit["sweetness"] > 5]
        assert color["a"] == [{"id": fruit["id"]} for fruit in sweet]
        assert color["b"] == [{"name": fruit["name"]} for fruit in sweet]
