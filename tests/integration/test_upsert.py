from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any, cast

import pytest
import strawberry
from sqlalchemy import Insert, insert, select

from strawchemy import Input, StrawchemyAsyncRepository, StrawchemySyncRepository
from strawchemy.repository.sqlalchemy._base import SQLAlchemyGraphQLRepository
from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit
from tests.integration.utils import data_argument
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from sqlalchemy import Select
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_OUT_OF_SCOPE = "Some rows to write do not exist or are not selected by the filter statement"

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Green"}]
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "best_time_to_pick": time(hour=9), "color_id": 1},
    {
        "id": 2,
        "name": "Cherry",
        "sweetness": 9,
        "water_percent": 0.93,
        "best_time_to_pick": time(hour=10, minute=30),
        "color_id": 1,
    },
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "sweetness", "water_percent", "color"], override=True)
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], override=True)
    class ColorType: ...

    # Generated primary keys are optional on create inputs, nested ones included, only under include="all".
    @strawchemy.create_input(Fruit, include="all")
    class FruitCreateInput: ...

    @strawchemy.pk_update_input(Fruit, include=["id", "name", "sweetness", "water_percent", "color"])
    class FruitUpdateInput: ...

    # Unused by root fields; declared so the nested `ColorFruitInput` gets an optional PK before
    # `ColorUpdateInput` builds it.
    @strawchemy.create_input(Color, include="all")
    class ColorCreateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name", "fruits"])
    class ColorUpdateInput: ...

    @strawchemy.upsert_update_fields(Fruit, include=["name", "sweetness", "water_percent", "best_time_to_pick"])
    class FruitUpsertFields: ...

    @strawchemy.upsert_conflict_fields(Fruit, include=["id", "name", "sweetness", "water_percent"])
    class FruitUpsertConflictFields: ...

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        update_fruit: FruitType = strawchemy.update_by_ids(FruitUpdateInput)
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)
        upsert_fruit: FruitType = strawchemy.upsert(
            FruitCreateInput, update_fields=FruitUpsertFields, conflict_fields=FruitUpsertConflictFields
        )
        upsert_fruits: list[FruitType] = strawchemy.upsert(
            FruitCreateInput, update_fields=FruitUpsertFields, conflict_fields=FruitUpsertConflictFields
        )

    conflict_on_id = cast("Any", FruitUpsertConflictFields).id

    @strawberry.type
    class AsyncMutation(Mutation):
        @strawchemy.field(graphql_type=list[FruitType], arguments=data_argument(list[FruitCreateInput]))
        async def upsert_fruits_restricted(
            self, info: strawberry.Info, data: list[FruitCreateInput]
        ) -> list[FruitType]:
            repo = StrawchemyAsyncRepository(FruitType, info, filter_statement=_apples())
            return (await repo.upsert(Input(data), conflict_fields=conflict_on_id)).graphql_list()

    @strawberry.type
    class SyncMutation(Mutation):
        @strawchemy.field(graphql_type=list[FruitType], arguments=data_argument(list[FruitCreateInput]))
        def upsert_fruits_restricted(self, info: strawberry.Info, data: list[FruitCreateInput]) -> list[FruitType]:
            repo = StrawchemySyncRepository(FruitType, info, filter_statement=_apples())
            return repo.upsert(Input(data), conflict_fields=conflict_on_id).graphql_list()

    is_async = issubclass(strawchemy.config.repository_type, StrawchemyAsyncRepository)
    return Operations(query=Query, mutation=AsyncMutation if is_async else SyncMutation)


def _apples() -> Select[Fruit]:
    return select(Fruit).where(Fruit.name == "Apple")


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS)]


@pytest.mark.snapshot
async def test_upsert_one_new(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test upserting a single new fruit record.

    This test verifies that the upsertFruit mutation correctly creates a new fruit
    record when no existing record matches. The test expects:
    - A successful GraphQL mutation response
    - The new fruit data to be returned correctly
    - Exactly 2 SQL queries: 1 INSERT and 1 SELECT
    """
    query = """
        mutation {
            upsertFruit(
                data: {
                    name: "Grape",
                    sweetness: 7,
                    waterPercent: 0.85
                }
            ) {
                name
                sweetness
                waterPercent
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["upsertFruit"] == {
        "name": "Grape",
        "sweetness": 7,
        "waterPercent": 0.85,
    }

    assert query_tracker.query_count == 2
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    ("query", "name", "sweetness", "water_percent"),
    [
        pytest.param(
            """
            mutation {
                upsertFruit(
                    data: {
                        name: "Apple",
                        sweetness: 0,
                        waterPercent: 0
                    },
                    conflictFields: name
                ) {
                    id
                    name
                    sweetness
                    waterPercent
                }
            }
            """,
            "Apple",
            0,
            0,
            id="unique-constraint",
        ),
        pytest.param(
            """
            mutation {
                upsertFruit(
                    data: {
                        name: "Almost Apple",
                        sweetness: 4,
                        waterPercent: 0.84
                    },
                    conflictFields: sweetnessAndWaterPercent
                ) {
                    id
                    name
                    sweetness
                    waterPercent
                }
            }
            """,
            "Almost Apple",
            4,
            0.84,
            id="unique-constraint-multi-columns",
        ),
        pytest.param(
            """
            mutation {
                upsertFruit(
                    data: {
                        id: 1
                        name: "Blueberries",
                        sweetness: 0,
                        waterPercent: 0
                    },
                    conflictFields: id
                ) {
                    id
                    name
                    sweetness
                    waterPercent
                }
            }
            """,
            "Blueberries",
            0,
            0,
            id="pk-constraint",
        ),
        pytest.param(
            """
            mutation {
                upsertFruit(
                    data: {
                        id: 1
                        name: "Blueberries",
                        sweetness: 0,
                        waterPercent: 0
                    },
                    conflictFields: id
                    updateFields: [ name ]
                ) {
                    id
                    name
                    sweetness
                    waterPercent
                }
            }
            """,
            "Blueberries",
            4,
            0.84,
            id="pk-constraint-update-fields",
        ),
    ],
)
@pytest.mark.snapshot
async def test_upsert_one_existing(
    query: str,
    name: str,
    sweetness: int,
    water_percent: float,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test upserting a single existing fruit record with conflict resolution.

    This test verifies that the upsertFruit mutation correctly updates an existing
    fruit record when a conflict is detected on the specified conflict field (name).
    The test expects:
    - A successful GraphQL mutation response with conflictFields specified
    - The existing fruit record to be updated with new values
    - The original ID to be preserved in the response
    - Exactly 2 SQL queries: 1 INSERT (with conflict resolution) and 1 SELECT
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["upsertFruit"] == {"id": 1, "name": name, "sweetness": sweetness, "waterPercent": water_percent}

    assert query_tracker.query_count == 2
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_upsert_many_new(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Test upserting multiple new fruit records.

    This test verifies that the upsertFruits mutation correctly creates multiple new
    fruit records when no existing records match. The test expects:
    - A successful GraphQL mutation response
    - All new fruit data to be returned in the correct order
    - Different SQL query patterns based on database dialect:
      * PostgreSQL/MySQL: 3 queries (2 INSERTs + 1 SELECT)
      * SQLite: 2 queries (1 batch INSERT + 1 SELECT)
    """
    query = """
        mutation {
            upsertFruits(
                data: [
                    {
                        name: "Grape",
                        sweetness: 7,
                        waterPercent: 0.85
                    },
                    {
                        name: "Blueberries",
                        sweetness: 6,
                        waterPercent: 0.93
                    },
                ]
            ) {
                name
                sweetness
                waterPercent
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["upsertFruits"] == [
        {"name": "Grape", "sweetness": 7, "waterPercent": 0.85},
        {"name": "Blueberries", "sweetness": 6, "waterPercent": 0.93},
    ]

    if dialect in {"postgresql", "mysql"}:
        assert query_tracker.query_count == 3
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    else:
        assert query_tracker.query_count == 2
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_upsert_many_new_and_existing(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Test upserting multiple fruits with mixed new and existing records.

    This test verifies that the upsertFruits mutation correctly handles a batch
    operation containing both new records (to be created) and existing records
    (to be updated) based on conflict resolution using the name field. The test expects:
    - A successful GraphQL mutation response with conflictFields specified
    - Mixed create/update operations to be handled correctly
    - All fruit data to be returned with updated values
    - Different SQL query patterns based on database dialect:
      * PostgreSQL/MySQL: 3 queries (2 INSERTs with conflict resolution + 1 SELECT)
      * SQLite: 2 queries (1 batch INSERT with conflict resolution + 1 SELECT)
    """
    query = """
        mutation {
            upsertFruits(
                data: [
                    {
                        name: "Apple",
                        sweetness: 7,
                        waterPercent: 0.85
                    },
                    {
                        name: "Blueberries",
                        sweetness: 6,
                        waterPercent: 0.93
                    },
                ],
                conflictFields: name
            ) {
                name
                sweetness
                waterPercent
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["upsertFruits"] == [
        {"name": "Apple", "sweetness": 7, "waterPercent": 0.85},
        {"name": "Blueberries", "sweetness": 6, "waterPercent": 0.93},
    ]

    if dialect in {"postgresql", "mysql"}:
        assert query_tracker.query_count == 3
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    else:
        assert query_tracker.query_count == 2
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


# To-One Upsert Tests


@pytest.mark.snapshot
async def test_to_one_upsert_create_new(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests upsert mutation that creates a new record when no match is found."""
    query = """
        mutation {
            updateFruit(
                data: {
                    id: 1,
                    name: "Grape",
                    sweetness: 7,
                    waterPercent: 0.85,
                    color: {
                        upsert: {
                            create: { name: "Purple" }
                        }
                    }
                }
            ) {
                id
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
    assert result.data["updateFruit"] == {
        "id": 1,
        "name": "Grape",
        "color": {"name": "Purple"},
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new color
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + new color


@pytest.mark.snapshot
async def test_to_one_upsert_update_existing(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests upsert mutation that updates an existing record when a match is found."""
    query = """
        mutation {
            updateFruit(
                data: {
                    id: 1,
                    name: "Apple - Granny smith",
                    color: {
                        upsert: {
                            create: { name: "Green" }
                            conflictFields: name
                        }
                    }
                }
            ) {
                id
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
    assert result.data["updateFruit"] == {
        "id": 1,
        "name": "Apple - Granny smith",
        "color": {"name": "Green"},
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)
    query_tracker.assert_statements(1, "update", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


# To-Many Upsert Tests


@pytest.mark.snapshot
async def test_to_many_upsert_create_new(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests to-many upsert mutation that creates new records."""
    query = """
        mutation {
            updateColor(
                data: {
                    id: 1,
                    name: "Bright Red",
                    fruits: {
                        upsert: {
                            create: [
                                { name: "Pomegranate", sweetness: 6, waterPercent: 0.82 },
                                { name: "Plums", sweetness: 7, waterPercent: 0.87 }
                            ]
                            conflictFields: name
                        }
                    }
                }
            ) {
                id
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

    assert result.data["updateColor"] == {
        "id": 1,
        "name": "Bright Red",
        "fruits": [{"name": "Apple"}, {"name": "Cherry"}, {"name": "Pomegranate"}, {"name": "Plums"}],
    }

    if dialect == "sqlite":
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruits


@pytest.mark.snapshot
async def test_to_many_upsert_update_existing(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests to-many upsert mutation that updates existing records."""
    query = """
        mutation {
            updateColor(
                data: {
                    id: 1,
                    name: "Bright Red",
                    fruits: {
                        upsert: {
                            create: [
                                { name: "Apple", sweetness: 6, waterPercent: 0.82 },
                                { name: "Cherry", sweetness: 7, waterPercent: 0.87 }
                            ]
                            conflictFields: name
                        }
                    }
                }
            ) {
                id
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

    assert result.data["updateColor"] == {
        "id": 1,
        "name": "Bright Red",
        "fruits": [{"name": "Apple"}, {"name": "Cherry"}],
    }

    if dialect == "sqlite":
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruits


@pytest.mark.parametrize(
    ("data", "expected", "names_after"),
    [
        pytest.param(
            '[{ id: 1, name: "Apple", sweetness: 5, waterPercent: 0.5 }]',
            [{"name": "Apple", "sweetness": 5}],
            ["Apple", "Cherry"],
            id="conflict-in-scope",
        ),
        pytest.param(
            '[{ id: 1, name: "Green apple", sweetness: 5, waterPercent: 0.5 }]',
            [{"name": "Green apple", "sweetness": 5}],
            ["Cherry", "Green apple"],
            id="conflict-moved-out",
        ),
        pytest.param(
            '[{ name: "Grape", sweetness: 7, waterPercent: 0.85 }]',
            [{"name": "Grape", "sweetness": 7}],
            ["Apple", "Cherry", "Grape"],
            id="insert-out-of-scope",
        ),
    ],
)
async def test_upsert_restricted_by_repository_statement(
    data: str, expected: list[dict[str, Any]], names_after: list[str], any_query: AnyQueryExecutor
) -> None:
    """A repository upsert under a filter statement returns the rows it wrote, even those the statement leaves out."""
    result = await maybe_async(any_query(f"mutation {{ upsertFruitsRestricted(data: {data}) {{ name sweetness }} }}"))
    assert not result.errors
    assert result.data
    assert result.data["upsertFruitsRestricted"] == expected

    result = await maybe_async(any_query("{ fruits { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(fruit["name"] for fruit in result.data["fruits"]) == names_after


@pytest.mark.parametrize(
    "data",
    [
        pytest.param('[{ id: 2, name: "Hacked", sweetness: 1, waterPercent: 0.5 }]', id="one"),
        pytest.param(
            '[{ id: 1, name: "Green apple", sweetness: 2, waterPercent: 0.6 }, '
            '{ id: 2, name: "Hacked", sweetness: 1, waterPercent: 0.5 }]',
            id="mixed",
        ),
        pytest.param(
            '[{ id: 3, name: "Grape", sweetness: 7, waterPercent: 0.85 }, '
            '{ id: 2, name: "Hacked", sweetness: 1, waterPercent: 0.5 }]',
            id="insert-and-conflict",
        ),
    ],
)
async def test_upsert_conflict_outside_repository_statement(data: str, any_query: AnyQueryExecutor) -> None:
    """A repository upsert conflicting with a row outside its filter statement fails and writes no row."""
    result = await maybe_async(any_query(f"mutation {{ upsertFruitsRestricted(data: {data}) {{ name }} }}"))
    assert result.errors
    assert result.errors[0].message == _OUT_OF_SCOPE

    result = await maybe_async(any_query("{ fruits { name sweetness } }"))
    assert not result.errors
    assert result.data
    assert sorted(result.data["fruits"], key=lambda fruit: fruit["name"]) == [
        {"name": "Apple", "sweetness": 4},
        {"name": "Cherry", "sweetness": 9},
    ]


async def test_upsert_conflict_update_bounded_by_repository_statement(
    any_query: AnyQueryExecutor, dialect: SupportedDialect, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upsert whose conflict pre-check misses a row outside its filter statement skips its update and fails."""
    if dialect == "mysql":
        pytest.skip("MySQL upserts take no WHERE: the pre-check alone bounds them")
    monkeypatch.setattr(SQLAlchemyGraphQLRepository, "_conflicting_keys_statement", lambda *_: None)
    result = await maybe_async(
        any_query(
            'mutation { upsertFruitsRestricted(data: [{ id: 2, name: "Hacked", sweetness: 1, waterPercent: 0.5 }]) '
            "{ name } }"
        )
    )
    assert result.errors
    assert result.errors[0].message == _OUT_OF_SCOPE

    result = await maybe_async(any_query("{ fruits { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(fruit["name"] for fruit in result.data["fruits"]) == ["Apple", "Cherry"]


@pytest.mark.snapshot
async def test_to_many_upsert_mixed_create_and_update(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests to-many upsert mutation that both creates new records and updates existing ones."""
    query = """
        mutation {
            updateColor(
                data: {
                    id: 1,
                    name: "Bright Red",
                    fruits: {
                        upsert: {
                            create: [
                                { name: "Plums", sweetness: 6, waterPercent: 0.82 },
                                { name: "Cherry", sweetness: 7, waterPercent: 0.87 }
                            ]
                            conflictFields: name
                        }
                    }
                }
            ) {
                id
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

    assert result.data["updateColor"] == {
        "id": 1,
        "name": "Bright Red",
        "fruits": [{"name": "Apple"}, {"name": "Cherry"}, {"name": "Plums"}],
    }

    if dialect == "sqlite":
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruits
