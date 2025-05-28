from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from syrupy.assertion import SnapshotAssertion
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .typing import RawRecordData

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


# Create tests


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createColor",
            """
            mutation {
                createColor(data: {  name: "new color" }) {
                    name
                }
            }
            """,
            id="createColor",
        ),
        pytest.param(
            "createValidatedColor",
            """
            mutation {
                createValidatedColor(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                }
            }
            """,
            id="createValidatedColor",
        ),
        pytest.param(
            "createColorManualValidation",
            """
            mutation {
                createColorManualValidation(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                }
            }
            """,
            id="createValidatedColor-manual",
        ),
        pytest.param(
            "createValidatedColor",
            """
            mutation {
                createValidatedColor(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            id="createValidatedColorAllFragments",
        ),
        pytest.param(
            "createColorManualValidation",
            """
            mutation {
                createColorManualValidation(data: {  name: "new color" }) {
                    ... on ColorType {
                        name
                    }
                    ... on ValidationErrorType {
                        id
                        errors {
                            id
                            loc
                            message
                            type
                        }
                    }
                }
            }
            """,
            id="createValidatedColorAllFragments-manual",
        ),
    ],
)
@pytest.mark.snapshot
async def test_create(
    query_name: str,
    query: str,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "new color"}

    insert_tracker, select_tracker = query_tracker.filter("insert"), query_tracker.filter("select")
    assert insert_tracker.query_count == 1
    assert select_tracker.query_count == 1
    assert insert_tracker[0].statement_formatted == sql_snapshot
    assert select_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_with_to_one_set(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
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
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
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
async def test_create_with_to_one_set_null(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
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
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new fruit", "color": None}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(1, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
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
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createFruit"] == {"name": "new color", "color": {"name": "new sub color"}}

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_to_one_create_and_nested_set(
    raw_topics: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
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
        any_query(query.format(topic_id=to_graphql_representation(raw_topics[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data["createUser"] == {
        "name": "Bob",
        "group": {"name": "new group", "topics": [{"id": to_graphql_representation(raw_topics[0]["id"], "output")}]},
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
async def test_create_with_to_many_create(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion, dialect: SupportedDialect
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
    result = await maybe_async(any_query(query))
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


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
            mutation {{
                createColor(data: {{
                    name: "new color",
                    fruits: {{
                        set: [ {{ id: {fruit_id} }} ],
                        add: [ {{ id: {fruit_id} }} ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                    }}
                }}
            }}
        """,
            id="add",
        ),
        pytest.param(
            """
            mutation {{
                createColor(data: {{
                    name: "new color",
                    fruits: {{
                        set: [ {{ id: {fruit_id} }} ],
                        create: [ {{ name: "new fruit 1", sweetness: 1, waterPercent: 0.8 }} ]
                    }}
                }}) {{
                    name
                    fruits {{
                        name
                    }}
                }}
            }}
        """,
            id="create",
        ),
    ],
)
async def test_create_with_to_many_set_exclusive_with_add_and_create(
    query: str, raw_fruits: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(
        any_query(query.format(fruit_id=to_graphql_representation(raw_fruits[0]["id"], "input")))
    )
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert result.errors[0].args[0] == "You cannot use `set` with `create` or `add` in -to-many relation input"


@pytest.mark.snapshot
async def test_create_with_to_many_create_and_nested_set(
    raw_farms: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
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
    result = await maybe_async(any_query(query.format(farm_id=to_graphql_representation(raw_farms[0]["id"], "input"))))
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {
        "name": "White",
        "fruits": [{"name": "Grape", "farms": [{"id": to_graphql_representation(raw_farms[0]["id"], "output")}]}],
    }

    query_tracker.assert_statements(1, "select", sql_snapshot)
    query_tracker.assert_statements(2, "insert", sql_snapshot)


@pytest.mark.snapshot
async def test_create_with_nested_mixed_relations_create(
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
                                sweetness: 1,
                                waterPercent: 0.8,
                                product: { create: { name: "wine" } }
                            },
                            {
                                name: "Lychee",
                                sweetness: 1,
                                waterPercent: 0.8,
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
    result = await maybe_async(any_query(query))
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
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion, dialect: SupportedDialect
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
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_create_init_defaults(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query(
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


# Update tests


@pytest.mark.parametrize(
    ("query", "query_name"),
    [
        pytest.param(
            """
                mutation {{
                    updateColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        id
                        name
                    }}
                }}
                """,
            "updateColor",
            id="no-validation",
        ),
        pytest.param(
            """
                mutation {{
                    updateValidatedColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        ... on ColorType {{
                            id
                            name
                        }}
                        ... on ValidationErrorType {{
                            errorId: id
                            errors {{
                                id
                                loc
                                message
                                type
                            }}
                        }}
                    }}
                }}
                """,
            "updateValidatedColor",
            id="validation-fragment",
        ),
        pytest.param(
            """
                mutation {{
                    updateValidatedColor(
                        data: {{
                            id: {color_id},
                            name: "updated color"
                        }}
                    ) {{
                        ... on ColorType {{
                            id
                            name
                        }}
                    }}
                }}
                """,
            "updateValidatedColor",
            id="validation-no-fragment",
        ),
    ],
)
@pytest.mark.snapshot
async def test_update(
    query_name: str,
    query: str,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests a simple update mutation."""
    result = await maybe_async(
        any_query(query.format(color_id=to_graphql_representation(raw_colors[0]["id"], "input")))
    )
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color",
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name


@pytest.mark.snapshot
async def test_update_by_filter(
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests a simple update mutation."""
    query = """
        mutation {
            updateColorsFilter(
                data: {
                    name: "updated color"
                },
                filter: {
                    name: { eq: "Red" }
                }
            ) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == [
        {
            "id": to_graphql_representation(raw_colors[0]["id"], "output"),
            "name": "updated color",
        }
    ]

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_by_filter_only_return_affected_objects(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion, dialect: SupportedDialect
) -> None:
    """Tests a simple update mutation."""
    query = """
        mutation {
            updateColorsFilter(
                data: {
                    name: "updated color"
                },
                filter: {
                    name: { eq: "unknown" }
                }
            ) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == []

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_one_set(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    # Use a different color to test the update
    color_id_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{ set: {{ id: {color_id_gql} }} }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name",
        "color": {"id": to_graphql_representation(raw_colors[1]["id"], "output")},
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_set_null(
    raw_fruits: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{ set: null }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name",
        "color": None,
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_create(
    raw_fruits: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating a new related record for a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name 2",
                    color: {{ create: {{ name: "newly created color during update" }} }}
                }}
            ) {{
                id
                name
                color {{
                    name
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(raw_fruits[0]["id"], "output"),
        "name": "updated fruit name 2",
        "color": {"name": "newly created color during update"},
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new color
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + new color


async def test_update_with_to_one_set_and_create_fail(
    raw_fruits: RawRecordData, raw_colors: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(raw_fruits[0]["id"], "input")
    # Use a different color to test the update
    color_id_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateFruit(
                data: {{
                    id: {fruit_id_gql},
                    name: "updated fruit name",
                    color: {{
                        set: {{ id: {color_id_gql} }},
                        create: {{ name: "newly created color during update" }}
                    }}
                }}
            ) {{
                id
                name
                color {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert result.errors[0].args[0] == "You cannot use both `set` and `create` in a -to-one relation input"


@pytest.mark.snapshot
async def test_update_with_to_one_create_and_nested_set(
    raw_users: RawRecordData,
    raw_topics: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a relationship."""
    user_id_gql = to_graphql_representation(raw_users[0]["id"], "input")
    # Use a different topic to test the update/create
    topic_id_gql = to_graphql_representation(raw_topics[1]["id"], "input")
    query = f"""
        mutation {{
            updateUser(
                data: {{
                    id: {user_id_gql},
                    name: "Updated Bob",
                    group: {{
                        create: {{
                            name: "new group during update",
                            topics: {{ set: [ {{ id: {topic_id_gql} }} ] }}
                        }}
                    }}
                }}
            ) {{
                id
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
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateUser"] == {
        "id": to_graphql_representation(raw_users[0]["id"], "output"),
        "name": "Updated Bob",
        "group": {
            "name": "new group during update",
            "topics": [{"id": to_graphql_representation(raw_topics[1]["id"], "output")}],
        },
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new group
    query_tracker.assert_statements(2, "update", sql_snapshot)  # Update user's group_id and topic's group id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated user + new group + topic


@pytest.mark.snapshot
async def test_update_with_to_many_set(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ set: [{{ id: {fruit_id_gql} }}] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [{"id": to_graphql_representation(raw_fruits[1]["id"], "output")}],
    }

    # 1. Disconnect previous fruit
    # 2. Update specified fruit's color_id
    # 3. Update color's name
    query_tracker.assert_statements(3, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_remove(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Remove the existing fruits
    fruit_ids_gql = [
        to_graphql_representation(fruit["id"], "input")
        for fruit in raw_fruits
        if fruit["color_id"] == raw_colors[0]["id"]
    ]
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ remove: [ {", ".join(f"{{ id: {fruit_id} }}" for fruit_id in fruit_ids_gql)} ] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [],
    }

    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_create(
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests updating a record and creating new related records for a to-many relationship."""
    color_id = raw_colors[0]["id"]
    color_id_gql = to_graphql_representation(color_id, "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name 2",
                    fruits: {{
                        create: [
                            {{ name: "new fruit 3 during update", sweetness: 1, waterPercent: 0.8 }},
                            {{ name: "new fruit 4 during update", sweetness: 1, waterPercent: 0.8 }}
                        ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name # Check names of newly created fruits
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # The order might vary, sort for assertion stability
    fruits_data = sorted(result.data["updateColor"]["fruits"], key=lambda x: x["name"])
    assert result.data["updateColor"]["id"] == to_graphql_representation(color_id, "output")
    assert result.data["updateColor"]["name"] == "updated color name 2"
    assert fruits_data == [
        *[{"name": fruit["name"]} for fruit in raw_fruits if fruit["color_id"] == color_id],
        {"name": "new fruit 3 during update"},
        {"name": "new fruit 4 during update"},
    ]

    # Insert 2 new fruits, in a single batched query
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "insert", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruits


@pytest.mark.snapshot
async def test_update_with_to_many_create_and_nested_set(
    raw_colors: RawRecordData,
    raw_farms: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a to-many relationship."""
    color_id = raw_colors[0]["id"]
    color_id_gql = to_graphql_representation(color_id, "input")
    # Use a different farm
    farm_id = raw_farms[-1]["id"]
    farm_id_gql = to_graphql_representation(farm_id, "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "Updated White",
                    fruits: {{
                        create: [
                            {{
                                name: "New Grape during update",
                                sweetness: 1,
                                waterPercent: 0.8,
                                farms: {{ set: [ {{ id: {farm_id_gql} }} ] }}
                            }}
                        ]
                    }}
                }}
            ) {{
                id
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
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    expected_fruits = [
        # Existing fruits
        *[
            {
                "name": fruit["name"],
                "farms": [
                    {
                        "id": to_graphql_representation(farm["id"], "output")  # noqa: B035
                        for farm in raw_farms
                        if farm["fruit_id"] == fruit["id"]
                    }
                ],
            }
            for fruit in raw_fruits
            if fruit["color_id"] == color_id
        ],
        # New one
        {
            "name": "New Grape during update",
            "farms": [{"id": to_graphql_representation(farm_id, "output")}],
        },
    ]
    for fruit in expected_fruits:
        assert fruit in result.data["updateColor"]["fruits"]

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new fruit
    query_tracker.assert_statements(2, "update", sql_snapshot)  # Update color name + fruit's farm_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated color + new fruit + farm


@pytest.mark.snapshot
async def test_update_with_to_many_add(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{ add: [{{ id: {fruit_id_gql} }}] }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(raw_colors[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [
            {"id": to_graphql_representation(raw_fruits[0]["id"], "output")},
            {"id": to_graphql_representation(raw_fruits[1]["id"], "output")},
        ],
    }

    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_add_and_create(
    raw_colors: RawRecordData,
    raw_fruits: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        add: [{{ id: {fruit_id_gql} }}],
                        create: [{{ name: "new fruit 3 during update", sweetness: 1, waterPercent: 0.8 }}]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"]["id"] == to_graphql_representation(raw_colors[0]["id"], "output")
    assert result.data["updateColor"]["name"] == "updated color name"
    expected = [
        {"name": to_graphql_representation(raw_fruits[0]["name"], "output")},
        {"name": "new fruit 3 during update"},
        {"name": to_graphql_representation(raw_fruits[1]["name"], "output")},
    ]
    for fruit in expected:
        assert fruit in result.data["updateColor"]["fruits"]

    query_tracker.assert_statements(1, "insert", sql_snapshot)
    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        add: [ {{ id: {fruit_id_gql} }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="add",
        ),
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        create: [ {{ name: "new fruit 3 during update", sweetness: 1, waterPercent: 0.8 }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="create",
        ),
        pytest.param(
            """
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name",
                    fruits: {{
                        set: [ {{ id: {fruit_id_gql} }} ]
                        remove: [ {{ id: {fruit_id_gql} }} ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    id
                }}
            }}
        }}
        """,
            id="remove",
        ),
    ],
)
async def test_update_with_to_many_set_exclusive_with_add_create_remove(
    query: str, raw_colors: RawRecordData, raw_fruits: RawRecordData, any_query: AnyQueryExecutor
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(raw_fruits[1]["id"], "input")
    result = await maybe_async(any_query(query.format(color_id_gql=color_id_gql, fruit_id_gql=fruit_id_gql)))
    assert not result.data
    assert result.errors
    assert len(result.errors) == 1
    assert (
        result.errors[0].args[0] == "You cannot use `set` with `create`, `add` or `remove` in a -to-many relation input"
    )


@pytest.mark.snapshot
async def test_update_with_nested_mixed_relations_create(
    raw_farms: RawRecordData,
    raw_fruits: RawRecordData,
    raw_colors: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Tests updating a record and creating multiple nested relations with different structures."""
    color_id = raw_colors[0]["id"]
    color_id_gql = to_graphql_representation(color_id, "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "Updated White 2",
                    fruits: {{
                        create: [
                            {{
                                name: "New Grape 2",
                                sweetness: 1,
                                waterPercent: 0.8,
                                product: {{ create: {{ name: "juice" }} }}
                            }},
                            {{
                                name: "New Lychee 2",
                                sweetness: 1,
                                waterPercent: 0.8,
                                farms: {{ create: [ {{ name: "Organic farm" }} ] }}
                            }},
                        ]
                    }}
                }}
            ) {{
                id
                name
                fruits {{
                    name
                    product {{ name }}
                    farms {{ name }}
                }}
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # Sort fruits for assertion stability
    fruits_data = sorted(result.data["updateColor"]["fruits"], key=lambda x: x["name"])
    assert result.data["updateColor"]["id"] == to_graphql_representation(color_id, "output")
    assert result.data["updateColor"]["name"] == "Updated White 2"
    expected_fruits = [
        # Existing fruits
        *[
            {
                "name": fruit["name"],
                "farms": [
                    {
                        "name": to_graphql_representation(farm["name"], "output")  # noqa: B035
                        for farm in raw_farms
                        if farm["fruit_id"] == fruit["id"]
                    }
                ],
                "product": None,
            }
            for fruit in raw_fruits
            if fruit["color_id"] == color_id
        ],
        # New ones
        {"name": "New Grape 2", "product": {"name": "juice"}, "farms": []},
        {"name": "New Lychee 2", "product": None, "farms": [{"name": "Organic farm"}]},
    ]
    for fruit in expected_fruits:
        assert fruit in fruits_data

    # Heterogeneous params means inserts cannot be batched
    query_tracker.assert_statements(4, "insert", sql_snapshot)  # product, farm, fruit1, fruit2
    query_tracker.assert_statements(1, "update", sql_snapshot)  # update color name
    query_tracker.assert_statements(1, "select", sql_snapshot)  # fetch updated color + new relations


@pytest.mark.snapshot
async def test_update_many(
    raw_colors: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating multiple records in a single mutation."""
    color_id1_gql = to_graphql_representation(raw_colors[0]["id"], "input")
    color_id2_gql = to_graphql_representation(raw_colors[1]["id"], "input")
    query = f"""
        mutation {{
            updateColors(
                data: [
                    {{ id: {color_id1_gql}, name: "batch updated color" }},
                    {{ id: {color_id2_gql}, name: "batch updated color" }}
                ]
            ) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    # Order might not be guaranteed, sort by ID
    updated_colors = sorted(result.data["updateColors"], key=lambda x: x["id"])
    expected_colors = sorted(
        [
            {"id": to_graphql_representation(raw_colors[0]["id"], "output"), "name": "batch updated color"},
            {"id": to_graphql_representation(raw_colors[1]["id"], "output"), "name": "batch updated color"},
        ],
        key=lambda x: x["id"],
    )
    assert updated_colors == expected_colors

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update colors in a single query
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated records


@pytest.mark.snapshot
async def test_update_no_init_defaults(
    raw_users: RawRecordData, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_query(
            f"""
            mutation {{
                updateUser(data: {{ id: {raw_users[3]["id"]}, name: "Jeanne" }}) {{
                    name
                    bio
                }}
            }}
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["updateUser"] == {"name": "Jeanne", "bio": raw_users[3]["bio"]}

    query_tracker.assert_statements(1, "update", sql_snapshot)


# Delete


@pytest.mark.snapshot
async def test_delete_filter(
    raw_users: RawRecordData,
    raw_groups: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    query = """
        mutation {
            deleteUsersFilter(
                filter: {
                    name: { eq: "Alice" }
                }
            ) {
                id
                name
                group {
                    name
                }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsersFilter"]) == 1
    apple_fruit = next(fruit for fruit in raw_users if fruit["name"] == "Alice")
    assert result.data["deleteUsersFilter"] == [
        {"id": apple_fruit["id"], "name": "Alice", "group": {"name": raw_groups[0]["name"]}}
    ]

    query_tracker.assert_statements(1, "delete", sql_snapshot)
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_delete_all(
    raw_users: RawRecordData,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    query = """
        mutation {
            deleteUsers {
                id
                name
                group {
                    name
                }
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsers"]) == len(raw_users)
    query_tracker.assert_statements(1, "delete", sql_snapshot)
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


# Custom mutations


@pytest.mark.snapshot
async def test_column_override(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = """
        mutation {
            createBlueColor(data: { name: "Green" }) {
                name
            }
        }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data["createBlueColor"] == {"name": "Blue"}
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createValidatedRankedUser",
            """
        mutation {
            createValidatedRankedUser(data: {  name: "batman" }) {
                ... on RankedUserType {
                    name
                    rank
                }
                ... on ValidationErrorType {
                    id
                    errors {
                        id
                        loc
                        message
                        type
                    }
                }
            }
        }
        """,
            id="validation",
        ),
        pytest.param(
            "createRankedUser",
            """
        mutation {
            createRankedUser(data: {  name: "batman" }) {
                name
                rank
            }
        }
        """,
            id="validation",
        ),
    ],
)
async def test_read_only_column_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "batman", "rank": 1}


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createAppleColor",
            """
                mutation {
                    createAppleColor(data: { name: "Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="not-existing",
        ),
        pytest.param(
            "createColorForExistingFruits",
            """
                mutation {
                    createColorForExistingFruits(data: { name: "Red" }) {
                        name
                        fruits {
                            name
                        }
                    }
                }
                """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_many_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "Red", "fruits": [{"name": "Apple"}, {"name": "Strawberry"}]}


@pytest.mark.parametrize(
    ("query_name", "query"),
    [
        pytest.param(
            "createRedFruit",
            """
            mutation {
                createRedFruit(data: { name: "Apple", sweetness: 1, waterPercent: 0.1 }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="not-existing",
        ),
        pytest.param(
            "createFruitForExistingColor",
            """
            mutation {
                createFruitForExistingColor(data: { name: "Apple", sweetness: 1, waterPercent: 0.1 }) {
                    name
                    color {
                        name
                    }
                }
            }
            """,
            id="existing",
        ),
    ],
)
async def test_relationship_to_one_override(query_name: str, query: str, any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert result.data[query_name] == {"name": "Apple", "color": {"name": "Red"}}
