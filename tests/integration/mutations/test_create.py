from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Department, Fruit, FruitFarm, Group, Topic, User
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: RawRecordData = [{"id": 1, "name": "Red"}]
_FRUITS: RawRecordData = [{"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1}]
_FARMS: RawRecordData = [{"id": 1, "name": "Apple farm", "fruit_id": 1}]
_GROUPS: RawRecordData = [{"id": 1, "name": "Group 1"}]
_TOPICS: RawRecordData = [{"id": 1, "name": "Hello!", "group_id": 1}]
# test_create_with_secondary_table_set pins IT's id.
_DEPARTMENTS: RawRecordData = [{"id": 1, "name": "IT"}]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "color", "farms", "product"], scope="schema")
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], scope="schema")
    class ColorType: ...

    @strawchemy.type(User, include=["name", "bio", "group", "departments"])
    class UserType: ...

    # Generated primary keys are optional on create inputs, nested ones included, only under include="all".
    @strawchemy.create_input(Fruit, include="all")
    class FruitCreateInput: ...

    @strawchemy.create_input(Color, include="all")
    class ColorCreateInput: ...

    @strawchemy.create_input(User, include="all")
    class UserCreate: ...

    # No case reads through it; a schema needs a query type.
    @strawberry.type
    class Query:
        colors: list[ColorType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        create_color: ColorType = strawchemy.create(ColorCreateInput)
        create_colors: list[ColorType] = strawchemy.create(ColorCreateInput)
        create_fruit: FruitType = strawchemy.create(FruitCreateInput)
        create_user: UserType = strawchemy.create(UserCreate)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Group).values(_GROUPS),
        insert(Topic).values(_TOPICS),
        insert(Color).values(_COLORS),
        insert(Fruit).values(_FRUITS),
        insert(FruitFarm).values(_FARMS),
        insert(Department).values(_DEPARTMENTS),
    ]


@pytest.mark.snapshot
async def test_create_with_to_one_set(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {{
            createFruit(data: {{
                name: "new fruit",
                sweetness: 1,
                waterPercent: 0.8,
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
    """
    result = await maybe_async(
        any_async_query(query.format(color_id=to_graphql_representation(_COLORS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {
        "name": "new fruit",
        "color": {"id": to_graphql_representation(_COLORS[0]["id"], "output")},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_set_null(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {{
            createFruit(data: {{
                name: "new fruit",
                sweetness: 1,
                waterPercent: 0.8,
                color: {{ set: null }}
            }}) {{
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(
        any_async_query(query.format(color_id=to_graphql_representation(_COLORS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new fruit", "color": None}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createFruit(data: {
                    name: "new color",
                    sweetness: 1,
                    waterPercent: 0.8,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new color", "color": {"name": "new sub color"}}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create_and_nested_set(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {{
                createUser(data: {{
                    name: "Bob",
                    group: {{
                        create: {{
                            name: "new group",
                            topics: {{ set: [ {{ id: {topic_id} }} ] }}
                        }}
                    }}
                }}) {{
                    name
                    group {{
                        name
                        topics {{
                            id
                        }}
                    }}
                }}
            }}
            """
    result = await maybe_async(
        any_async_query(query.format(topic_id=to_graphql_representation(_TOPICS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createUser"] == {
        "name": "Bob",
        "group": {"name": "new group", "topics": [{"id": to_graphql_representation(_TOPICS[0]["id"], "output")}]},
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


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
        ),
        pytest.param(
            """
        mutation {{
            createColor(data: {{
                name: "new color",
                fruits: {{
                    add: [{{ id: {fruit_id} }}]
                }}
            }}) {{
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="add",
        ),
    ],
)
@pytest.mark.snapshot
async def test_create_with_existing_to_many(
    query: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query(query.format(fruit_id=to_graphql_representation(_FRUITS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"id": to_graphql_representation(_FRUITS[0]["id"], "output")}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "update", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_many_create(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "new color",
                    fruits: {
                        create: [
                            { name: "new fruit 1", sweetness: 1, waterPercent: 0.8 },
                            { name: "new fruit 2", sweetness: 2, waterPercent: 0.9 }
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "new color",
        "fruits": [{"name": "new fruit 1"}, {"name": "new fruit 2"}],
    }
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(3, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_many_create_and_nested_set(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {{
                createColor(data: {{
                    name: "White",
                    fruits: {{
                        create: [
                            {{
                                name: "Grape",
                                sweetness: 1,
                                waterPercent: 0.8,
                                farms: {{ set: [ {{ id: {farm_id} }} ] }}
                            }},
                        ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                        farms {{
                            id
                        }}
                    }}
                }}
            }}
            """
    result = await maybe_async(
        any_async_query(query.format(farm_id=to_graphql_representation(_FARMS[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "White",
        "fruits": [{"name": "Grape", "farms": [{"id": to_graphql_representation(_FARMS[0]["id"], "output")}]}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_nested_mixed_relations_create(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createColor(data: {
                    name: "White",
                    fruits: {
                        create: [
                            {
                                name: "Grape",
                                sweetness: 1,
                                waterPercent: 0.8,
                                product: { create: { name: "wine" } }
                            },
                            {
                                name: "Lychee",
                                sweetness: 1,
                                waterPercent: 0.7,
                                farms: { create: [ { name: "Bio farm" } ] }
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createColor"]["name"] == "White"
    expected_fruits = [
        {"name": "Lychee", "product": None, "farms": [{"name": "Bio farm"}]},
        {"name": "Grape", "product": {"name": "wine"}, "farms": []},
    ]
    for fruit in expected_fruits:
        assert fruit in result.data["createColor"]["fruits"]

    # Heterogeneous params means inserts cannot be batched
    query_tracker.assert_statements(5, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_many(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    result = await maybe_async(
        any_async_query(
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
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_init_defaults(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query(
            """
            mutation {
                createUser(data: { name: "Jeanne" }) {
                    name
                    bio
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["createUser"] == {
        "name": "Jeanne",
        "bio": "Lorem ipsum dolor sit amet, consectetur adipiscing elit",
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_secondary_table_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createUser(
                    data: {
                        name: "Astrid",
                        departments: { set: [ { id: 1 } ] }
                    }
                ) {
                    name
                    departments {
                        id
                        name
                    }
                }
            }
            """

    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert result.data["createUser"] == {"name": "Astrid", "departments": [{"id": 1, "name": "IT"}]}

    insert_tracker, select_tracker = query_tracker.filter("insert"), query_tracker.filter("select")
    assert insert_tracker.query_count == 2
    assert select_tracker.query_count == 1
    assert insert_tracker[0].statement_formatted == sql_snapshot
    assert select_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_with_secondary_table_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
            mutation {
                createUser(
                    data: {
                        name: "Astrid",
                        departments: { create: [ { name: "Support" } ] }
                    }
                ) {
                    name
                    departments {
                        name
                    }
                }
            }
            """

    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createUser"] == {"name": "Astrid", "departments": [{"name": "Support"}]}

    query_tracker.assert_statements(3, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)
