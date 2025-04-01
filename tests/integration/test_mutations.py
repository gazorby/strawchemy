from __future__ import annotations

from uuid import uuid4

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from syrupy.assertion import SnapshotAssertion
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import ColorCreateInput, ColorType, FruitCreateInput, FruitType, strawchemy
from .typing import RawRecordData

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncMutation:
    create_color: ColorType = strawchemy.create_mutation(ColorCreateInput, repository_type=StrawchemyAsyncRepository)
    create_colors: list[ColorType] = strawchemy.create_mutation(
        ColorCreateInput, repository_type=StrawchemyAsyncRepository
    )

    create_fruit: FruitType = strawchemy.create_mutation(FruitCreateInput, repository_type=StrawchemyAsyncRepository)
    create_fruits: list[FruitType] = strawchemy.create_mutation(
        FruitCreateInput, repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncMutation:
    create_color: ColorType = strawchemy.create_mutation(ColorCreateInput, repository_type=StrawchemySyncRepository)
    create_colors: list[ColorType] = strawchemy.create_mutation(
        ColorCreateInput, repository_type=StrawchemySyncRepository
    )

    create_fruit: FruitType = strawchemy.create_mutation(FruitCreateInput, repository_type=StrawchemySyncRepository)
    create_fruits: list[FruitType] = strawchemy.create_mutation(
        FruitCreateInput, repository_type=StrawchemySyncRepository
    )


@pytest.fixture
def sync_mutation() -> type[SyncMutation]:
    return SyncMutation


@pytest.fixture
def async_mutation() -> type[AsyncMutation]:
    return AsyncMutation


@pytest.mark.snapshot
async def test_create_mutation(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query('mutation { createColor(data: {  name: "new color" }) { name } }'))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {"name": "new color"}

    insert_tracker, select_tracker = query_tracker.filter("insert"), query_tracker.filter("select")
    assert insert_tracker.query_count == 1
    assert select_tracker.query_count == 1
    assert insert_tracker[0].statement_formatted == sql_snapshot
    assert select_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
            mutation {{
                createColor(data: {{
                    name: "new color",
                    fruits: {{
                        set: [{{ id: {fruit_id} }}]
                    }}
                }}) {{
                    name
                    fruits {{
                        id
                    }}
                }}
            }}
            """,
            id="set",
        )
    ],
)
@pytest.mark.snapshot
async def test_create_mutation_nested_to_many(
    query: str,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(
        any_query(query.format(fruit_id=to_graphql_representation(raw_fruits[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"id": to_graphql_representation(raw_fruits[0]["id"], "output")}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "update", sql_snapshot)


@pytest.mark.snapshot
async def test_create_mutation_nested_to_many_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "new color",
                    fruits: {
                        create: [
                            { name: "new fruit 1", adjectives: ["foo"] },
                            { name: "new fruit 2", adjectives: ["bar"] }
                        ]
                    }
                }) {
                    name
                    fruits {
                        name
                    }
                }
            }
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"name": "new fruit 1"}, {"name": "new fruit 2"}],
    }

    query_tracker.assert_statements(2, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
            mutation {{
                createFruit(data: {{
                    name: "new fruit",
                    adjectives: ["foo", "bar"],
                    color: {{
                        set: {{ id: {color_id} }}
                    }}
                }}) {{
                    name
                    color {{
                        id
                    }}
                }}
            }}
            """,
            id="set",
        )
    ],
)
@pytest.mark.snapshot
async def test_create_mutation_nested_to_one(
    query: str,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    fruit_id = uuid4()
    result = await maybe_async(
        any_query(query.format(fruit_id=fruit_id, color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {
        "name": "new fruit",
        "color": {"id": to_graphql_representation(raw_colors[0]["id"], "output")},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_mutation_nested_mixed_relations_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "White",
                    fruits: {
                        create: [
                            {
                                name: "Grape",
                                product: { create: { name: "wine" } },
                                adjectives: ["tangy", "juicy"]
                            },
                            {
                                name: "Lychee",
                                farms: { create: [ { name: "Bio farm" } ] },
                                adjectives: ["sweet", "floral"]
                            },
                        ]
                    }
                }) {
                    name
                    fruits {
                        name
                        product {
                            name
                        }
                        farms {
                            name
                        }
                    }
                }
            }
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "White",
        "fruits": [
            {"name": "Lychee", "product": None, "farms": [{"name": "Bio farm"}]},
            {"name": "Grape", "product": {"name": "wine"}, "farms": []},
        ],
    }

    # Heterogeneous params means inserts cannot be batched
    query_tracker.assert_statements(5, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_mutation_nested_to_one_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createFruit(data: {
                    name: "new color",
                    adjectives: ["foo", "bar"],
                    color: {
                        create: { name: "new sub color" }
                    }
                }) {
                    name
                    color {
                        name
                    }
                }
            }
            """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new color", "color": {"name": "new sub color"}}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_many_mutation(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query(
            """
                mutation {
                    createColors(
                        data: [
                            { name: "new color 1" }
                            { name: "new color 2" }
                        ]
                    ) {
                        name
                    }
                }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["createColors"] == [{"name": "new color 1"}, {"name": "new color 2"}]

    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)
