from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm, User
from tests.integration.utils import compute_aggregation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from decimal import Decimal

    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Names do not follow id order. Every color holds at least two fruits, so sample statistics of their water percent
# are defined, and water percent is set so that every aggregation ranks the colors neither by id nor in reverse.
_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}, {"id": 3, "name": "Green"}]
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.24, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.22, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.68, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 1, "water_percent": 0.79, "color_id": 2},
    {"id": 5, "name": "Quince", "sweetness": 3, "water_percent": 0.86, "color_id": 2},
    {"id": 6, "name": "Strawberry", "sweetness": 5, "water_percent": 0.4, "color_id": 3},
    {"id": 7, "name": "Cantaloupe", "sweetness": 0, "water_percent": 0.41, "color_id": 3},
]
# Apple and Cherry hold more farms than the other fruits, which all tie on one farm.
_FRUIT_FARMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Apple farm 3", "fruit_id": 1},
    {"id": 4, "name": "Cherry farm", "fruit_id": 2},
    {"id": 5, "name": "Cherry farm 2", "fruit_id": 2},
    {"id": 6, "name": "Banana farm", "fruit_id": 3},
    {"id": 7, "name": "Lemon farm", "fruit_id": 4},
    {"id": 8, "name": "Quince farm", "fruit_id": 5},
    {"id": 9, "name": "Strawberry farm", "fruit_id": 6},
    {"id": 10, "name": "Cantaloupe farm", "fruit_id": 7},
]
# Two users have a bio and two do not, so null ordering moves rows around the non-null ones.
_USERS: list[dict[str, Any]] = [
    {"id": 1, "name": "Alice", "bio": None},
    {"id": 2, "name": "Bob", "bio": "Beta bio"},
    {"id": 3, "name": "Charlie", "bio": None},
    {"id": 4, "name": "Tango", "bio": "Alpha bio"},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(User, include=["id", "name", "bio"])
    class UserType: ...

    @strawchemy.order(User, include=["id", "bio"])
    class UserOrderBy: ...

    @strawchemy.type(Fruit, include=["id", "name", "sweetness", "water_percent"], scope="schema")
    class FruitType: ...

    # The order list also filters the order inputs of `fruits` (nested ordering and aggregations) and of their `color`.
    @strawchemy.type(
        Color,
        include=["id", "name", "fruits"],
        order=["id", "name", "sweetness", "water_percent", "fruits"],
        scope="schema",
    )
    class ColorType: ...

    @strawchemy.type(
        Color,
        include=["id", "name", "fruits"],
        order=["id", "name", "sweetness", "water_percent", "fruits"],
        paginate=["fruits"],
    )
    class ColorTypeWithPagination: ...

    @strawchemy.order(Fruit, include=["id", "sweetness", "color"])
    class FruitOrderBy: ...

    @strawchemy.order(Color, include=["id", "name", "fruits"])
    class ColorOrder: ...

    @strawchemy.distinct_on(Color, include=["name"])
    class ColorDistinctOn: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field(order_by_input=UserOrderBy)
        fruits: list[FruitType] = strawchemy.field(order_by_input=FruitOrderBy)
        colors: list[ColorType] = strawchemy.field(order_by_input=ColorOrder, distinct_on=ColorDistinctOn)
        colors_paginated: list[ColorTypeWithPagination] = strawchemy.field(pagination=True)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Color).values(_COLORS),
        insert(Fruit).values(_FRUITS),
        insert(FruitFarm).values(_FRUIT_FARMS),
        insert(User).values(_USERS),
    ]


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by(
    order_by: Literal["ASC", "DESC"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(f"{{ fruits(orderBy: {{ sweetness: {order_by} }}) {{ id sweetness }} }}")
    )
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [{"id": row["id"], "sweetness": row["sweetness"]} for row in _FRUITS]
    expected_sort = sorted(expected_sort, key=lambda x: x["sweetness"], reverse=order_by == "DESC")
    assert [{"id": row["id"], "sweetness": row["sweetness"]} for row in result.data["fruits"]] == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"])
@pytest.mark.snapshot
async def test_nulls(
    order_by: Literal["ASC_NULLS_FIRST", "ASC_NULLS_LAST", "DESC_NULLS_FIRST", "DESC_NULLS_LAST"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query(f"{{ users(orderBy: {{ bio: {order_by} }}) {{ id bio }} }}"))
    assert not result.errors
    assert result.data
    # Sort records
    expected_sort = [{"id": row["id"], "bio": row["bio"]} for row in _USERS if row["bio"] is not None]
    nulls = [{"id": row["id"], "bio": row["bio"]} for row in _USERS if row["bio"] is None]
    expected_sort = sorted(expected_sort, key=lambda x: x["bio"], reverse=order_by.startswith("DESC"))
    expected_sort = expected_sort + nulls if order_by.endswith("LAST") else nulls + expected_sort
    actual_sort = [{"id": row["id"], "bio": row["bio"]} for row in result.data["users"]]
    assert actual_sort == expected_sort
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "aggregation",
    ["max", "min", "sum", "avg", "stddevSamp", "stddevPop", "varSamp", "varPop"],
)
@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_order_by_aggregations(
    order_by: Literal["ASC", "DESC"],
    aggregation: Literal["max", "min", "sum", "avg", "varPop", "stddevPop", "varSamp", "stddevSamp"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    db_features: DatabaseFeatures,
) -> None:
    if aggregation not in db_features.aggregation_functions:
        pytest.skip(f"{db_features.dialect} does not support {aggregation} aggregation function")

    result = await maybe_async(
        any_async_query(
            f"""{{
            colors(orderBy: {{ fruitsAggregate: {{ {aggregation}: {{ waterPercent: {order_by} }} }} }}) {{
                id
                fruits {{
                    waterPercent
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    water_percent_map: dict[str, float | Decimal] = {
        color["id"]: compute_aggregation(
            aggregation, [fruit["water_percent"] for fruit in _FRUITS if fruit["color_id"] == color["id"]]
        )
        for color in _COLORS
    }
    expected_order = sorted(water_percent_map, key=lambda id_: water_percent_map[id_], reverse=order_by == "DESC")
    assert [row["id"] for row in result.data["colors"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_relation_order_by(
    order_by: Literal["ASC", "DESC"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            f"""{{
            colors {{
                id
                fruits(orderBy: {{ sweetness: {order_by} }}) {{
                    sweetness
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = sorted(
            (fruit["sweetness"] for fruit in _FRUITS if fruit["color_id"] == color["id"]), reverse=order_by == "DESC"
        )
        assert [row["sweetness"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_relation_order_by_unselected_column(
    order_by: Literal["ASC", "DESC"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            f"""{{
            colors {{
                id
                fruits(orderBy: {{ sweetness: {order_by} }}) {{
                    name
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = [
            fruit["name"]
            for fruit in sorted(
                (fruit for fruit in _FRUITS if fruit["color_id"] == color["id"]),
                key=lambda fruit: fruit["sweetness"],
                reverse=order_by == "DESC",
            )
        ]
        assert [row["name"] for row in color["fruits"]] == expected_order
        assert all(set(row) == {"name"} for row in color["fruits"])

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


def _color_fruits(color_id: int) -> list[dict[str, Any]]:
    return [fruit for fruit in _FRUITS if fruit["color_id"] == color_id]


def _farm_count(fruit_id: int) -> int:
    return sum(1 for farm in _FRUIT_FARMS if farm["fruit_id"] == fruit_id)


def _colors_with_fruit_ids(colors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": color["id"], "fruits": [{"id": fruit["id"]} for fruit in _color_fruits(color["id"])]} for color in colors
    ]


@pytest.mark.snapshot
async def test_relation_order_by_nested_relation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            """{
            colors {
                id
                fruits(orderBy: [{ color: { name: ASC } }, { sweetness: DESC }]) {
                    name
                    sweetness
                }
            }
        }"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = [
            fruit["name"] for fruit in sorted(_color_fruits(color["id"]), key=lambda fruit: -fruit["sweetness"])
        ]
        assert [row["name"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize("order_by", ["ASC", "DESC"])
@pytest.mark.snapshot
async def test_relation_order_by_nested_aggregation(
    order_by: Literal["ASC", "DESC"],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            f"""{{
            colors {{
                id
                fruits(orderBy: [{{ farmsAggregate: {{ count: {order_by} }} }}, {{ sweetness: ASC }}]) {{
                    name
                    sweetness
                }}
            }}
        }}"""
        )
    )
    assert not result.errors
    assert result.data

    direction = -1 if order_by == "DESC" else 1
    for color in result.data["colors"]:
        expected_order = [
            fruit["name"]
            for fruit in sorted(
                _color_fruits(color["id"]),
                key=lambda fruit: (direction * _farm_count(fruit["id"]), fruit["sweetness"]),
            )
        ]
        assert [row["name"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_relation_order_by_nested_relation_aggregation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            """{
            colors {
                id
                fruits(orderBy: [{ color: { fruitsAggregate: { count: ASC } } }, { sweetness: DESC }]) {
                    name
                    sweetness
                }
            }
        }"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = [
            fruit["name"] for fruit in sorted(_color_fruits(color["id"]), key=lambda fruit: -fruit["sweetness"])
        ]
        assert [row["name"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_paginated_relation_order_by_nested_aggregation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            """{
            colorsPaginated {
                id
                fruits(limit: 1, orderBy: [{ farmsAggregate: { count: DESC } }, { sweetness: ASC }]) {
                    name
                    sweetness
                }
            }
        }"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colorsPaginated"]:
        expected_order = sorted(
            _color_fruits(color["id"]),
            key=lambda fruit: (-_farm_count(fruit["id"]), fruit["sweetness"]),
        )
        assert [row["name"] for row in color["fruits"]] == [expected_order[0]["name"]]

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_paginated_relation_order_by_nested_relation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            """{
            colorsPaginated {
                id
                fruits(limit: 1, offset: 1, orderBy: [{ color: { name: ASC } }, { sweetness: DESC }]) {
                    name
                    sweetness
                }
            }
        }"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colorsPaginated"]:
        expected_order = sorted(_color_fruits(color["id"]), key=lambda fruit: -fruit["sweetness"])
        assert [row["name"] for row in color["fruits"]] == [expected_order[1]["name"]]

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_distinct_on_with_relation_order_by_nested_aggregation(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_async_query(
            """{
            colors(distinctOn: [name], orderBy: [{ name: ASC }]) {
                id
                fruits(orderBy: [{ farmsAggregate: { count: ASC } }, { sweetness: DESC }]) {
                    name
                    sweetness
                }
            }
        }"""
        )
    )
    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        expected_order = [
            fruit["name"]
            for fruit in sorted(
                _color_fruits(color["id"]),
                key=lambda fruit: (_farm_count(fruit["id"]), -fruit["sweetness"]),
            )
        ]
        assert [row["name"] for row in color["fruits"]] == expected_order

    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_deterministic_ordering(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that list resolvers return ordered results even if no order by is specified."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colors {
                    id
                    fruits {
                        id
                    }
                }
            }
        """
        )
    )
    assert not result.errors
    assert result.data

    assert result.data["colors"] == _colors_with_fruit_ids(_COLORS)
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_deterministic_ordering_mixed_with_user_ordering(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that list resolvers return ordered results even if no order by is specified."""
    result = await maybe_async(
        any_async_query(
            """
            {
                colors(orderBy: { name: ASC }) {
                    id
                    fruits {
                        id
                    }
                }
            }
        """
        )
    )
    assert not result.errors
    assert result.data

    assert result.data["colors"] == _colors_with_fruit_ids(sorted(_COLORS, key=lambda color: color["name"]))
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("query", "variables"),
    [
        pytest.param("{ colors(orderBy: {}) { id fruits { id } } }", None, id="root-empty"),
        pytest.param("{ colors(orderBy: [{}]) { id fruits { id } } }", None, id="root-empty-list"),
        pytest.param(
            "query ($d: OrderByEnum) { colors(orderBy: { name: $d }) { id fruits { id } } }",
            {},
            id="root-omitted-variable",
        ),
        pytest.param("{ colors { id fruits(orderBy: {}) { id } } }", None, id="nested-empty"),
        pytest.param("{ colors { id fruits(orderBy: [{}]) { id } } }", None, id="nested-empty-list"),
        pytest.param(
            "query ($d: OrderByEnum) { colors { id fruits(orderBy: { sweetness: $d }) { id } } }",
            {},
            id="nested-omitted-variable",
        ),
        pytest.param("{ colors { id fruits(orderBy: { color: {} }) { id } } }", None, id="nested-empty-relation"),
        pytest.param(
            "{ colors { id fruits(orderBy: { color: { fruits: {} } }) { id } } }",
            None,
            id="nested-empty-nested-relation",
        ),
        pytest.param("{ colors(orderBy: { name: null }) { id fruits { id } } }", None, id="root-null"),
        pytest.param("{ colors(orderBy: null) { id fruits { id } } }", None, id="root-null-argument"),
        pytest.param("{ colors { id fruits(orderBy: { color: null }) { id } } }", None, id="nested-null-relation"),
        pytest.param(
            "{ colors { id fruits(orderBy: { color: { name: null } }) { id } } }",
            None,
            id="nested-null-in-relation",
        ),
        pytest.param(
            "query ($d: OrderByEnum) { colors(orderBy: { name: $d }) { id fruits { id } } }",
            {"d": None},
            id="root-null-variable",
        ),
    ],
)
async def test_empty_order_by_is_ignored(
    query: str,
    variables: dict[str, Any] | None,
    any_async_query: AnyQueryExecutor,
) -> None:
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data
    assert result.data["colors"] == _colors_with_fruit_ids(_COLORS)


@pytest.mark.parametrize(
    ("empty_entry", "variables"),
    [
        pytest.param("{}", None, id="empty"),
        pytest.param("{ color: {} }", None, id="empty-relation"),
        pytest.param("{ color: { fruits: {} } }", None, id="empty-nested-relation"),
        pytest.param("{ color: { name: $d } }", {}, id="omitted-variable-in-relation"),
        pytest.param("{ color: null, sweetness: null }", None, id="null"),
        pytest.param("{ color: { name: $d } }", {"d": None}, id="null-variable-in-relation"),
    ],
)
async def test_empty_order_by_entry_keeps_other_entries(
    empty_entry: str,
    variables: dict[str, Any] | None,
    any_async_query: AnyQueryExecutor,
) -> None:
    signature = "query ($d: OrderByEnum) " if variables is not None else ""
    result = await maybe_async(
        any_async_query(
            f"{signature}{{ fruits(orderBy: [{{ color: {{}}, sweetness: ASC }}, {empty_entry}, {{ id: DESC }}]) {{ id }} }}",
            variables,
        )
    )
    assert not result.errors
    assert result.data
    expected = [fruit["id"] for fruit in sorted(_FRUITS, key=lambda fruit: (fruit["sweetness"], -fruit["id"]))]
    assert [row["id"] for row in result.data["fruits"]] == expected


@pytest.mark.parametrize(
    ("empty_entry", "variables"),
    [
        pytest.param("{}", None, id="empty"),
        pytest.param("{ fruitsAggregate: {} }", None, id="empty-aggregate"),
        pytest.param("{ fruitsAggregate: { max: {} } }", None, id="empty-aggregate-function"),
        pytest.param("{ fruitsAggregate: { count: $d } }", {}, id="omitted-variable-in-aggregate"),
    ],
)
async def test_empty_order_by_entry_keeps_other_entries_nested(
    empty_entry: str,
    variables: dict[str, Any] | None,
    any_async_query: AnyQueryExecutor,
) -> None:
    signature = "query ($d: OrderByEnum) " if variables is not None else ""
    result = await maybe_async(
        any_async_query(
            f"""{signature}{{
            colors(orderBy: [{empty_entry}, {{ id: DESC }}]) {{
                id
                fruits(orderBy: [{{}}, {{ color: {{ fruits: {{}} }}, sweetness: DESC }}, {{ color: {{}} }}, {{ id: DESC }}]) {{
                    id
                }}
            }}
        }}""",
            variables,
        )
    )
    assert not result.errors
    assert result.data
    expected = [
        {
            "id": color["id"],
            "fruits": [
                {"id": fruit["id"]}
                for fruit in sorted(_color_fruits(color["id"]), key=lambda fruit: (-fruit["sweetness"], -fruit["id"]))
            ],
        }
        for color in sorted(_COLORS, key=lambda color: -color["id"])
    ]
    assert result.data["colors"] == expected
