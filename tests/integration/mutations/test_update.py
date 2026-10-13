from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, insert, select

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Department, Fruit, FruitFarm, Group, Topic, User, UserDepartmentJoinTable
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.repository.typing import AnySession
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Only Alice has a group and only Tango has a bio; Tango belongs to no department and Charlie to two.
# The restricted mutations pin Bob's id.
_USERS: RawRecordData = [
    {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
    {"id": 2, "name": "Bob", "group_id": None, "bio": None},
    {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
    {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
]
# Secondary-table cases pin IT's id.
_DEPARTMENTS: RawRecordData = [
    {"id": 1, "name": "IT"},
    {"id": 2, "name": "Sales"},
    {"id": 3, "name": "Platform"},
]
_USER_DEPARTMENTS: RawRecordData = [
    {"user_id": 1, "department_id": 1},
    {"user_id": 2, "department_id": 2},
    {"user_id": 3, "department_id": 3},
    {"user_id": 3, "department_id": 1},
]

_COLORS: RawRecordData = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Orange"},
]
# Red, Yellow and Orange hold 2, 3 and 2 fruits, which the fruit count filters tell apart; Orange and
# clementine are sweeter than 5 without being red.
_FRUITS: RawRecordData = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
    {"id": 4, "name": "Lemon", "sweetness": 1, "water_percent": 0.88, "color_id": 2},
    {"id": 5, "name": "Quince", "sweetness": 3, "water_percent": 0.81, "color_id": 2},
    {"id": 6, "name": "Orange", "sweetness": 8, "water_percent": 0.86, "color_id": 3},
    {"id": 7, "name": "clementine", "sweetness": 14, "water_percent": 0.9, "color_id": 3},
]
# The last farm grows a fruit that is not red.
_FARMS: RawRecordData = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Cherry farm", "fruit_id": 2},
    {"id": 3, "name": "Orange farm", "fruit_id": 6},
]
# Group 2 is Charlie's group in test_update_filter_counting_the_table_next_to_two_to_many_paths, and
# its topic is the one test_update_with_to_one_create_and_nested_set moves.
_GROUPS: RawRecordData = [{"id": 1, "name": "Group 1"}, {"id": 2, "name": "Group 2"}]
_TOPICS: RawRecordData = [
    {"id": 1, "name": "Hello!", "group_id": 1},
    {"id": 2, "name": "Problems", "group_id": 2},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "sweetness", "color", "farms", "product"], override=True)
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], override=True)
    class ColorType: ...

    @strawchemy.type(User, include=["id", "name", "bio", "group", "departments"])
    class UserType: ...

    # The include list also filters the count arguments of the color filter's `fruitsAggregate`: cases count on `id`.
    @strawchemy.filter(Fruit, include=["id", "sweetness", "color"])
    class FruitFilter: ...

    @strawchemy.filter(Color, include=["name", "fruits"])
    class ColorFilter: ...

    # The include list also filters the count arguments of the aggregations below it: cases count on `id`.
    @strawchemy.filter(User, include=["id", "name", "bio", "group", "departments"])
    class UserFilter: ...

    @strawchemy.filter_update_input(Fruit, include=["sweetness"])
    class FruitPartial: ...

    @strawchemy.filter_update_input(Color, include=["name"])
    class ColorPartial: ...

    @strawchemy.filter_update_input(User, include=["name"])
    class UserPartial: ...

    # Unused by root fields; gives the nested create inputs below optional generated PKs, only under include="all".
    @strawchemy.create_input(Fruit, include="all")
    class FruitCreateInput: ...

    @strawchemy.create_input(Color, include="all")
    class ColorCreateInput: ...

    @strawchemy.create_input(User, include="all")
    class UserCreate: ...

    @strawchemy.pk_update_input(Fruit, include=["id", "name", "color"])
    class FruitUpdateInput: ...

    @strawchemy.pk_update_input(Color, include=["id", "name", "fruits"])
    class ColorUpdateInput: ...

    @strawchemy.pk_update_input(User, include=["id", "name", "group", "departments"])
    class UserUpdateInput: ...

    @strawberry.type
    class Query:
        fruits: list[FruitType] = strawchemy.field(filter_input=FruitFilter)
        colors: list[ColorType] = strawchemy.field(filter_input=ColorFilter)
        users: list[UserType] = strawchemy.field(filter_input=UserFilter)

    @strawberry.type
    class Mutation:
        update_color: ColorType = strawchemy.update_by_ids(ColorUpdateInput)
        update_colors: list[ColorType] = strawchemy.update_by_ids(ColorUpdateInput)
        update_colors_filter: list[ColorType] = strawchemy.update(ColorPartial, ColorFilter)
        update_fruit: FruitType = strawchemy.update_by_ids(FruitUpdateInput)
        update_fruits_filter: list[FruitType] = strawchemy.update(FruitPartial, FruitFilter)
        update_user: UserType = strawchemy.update_by_ids(UserUpdateInput)
        update_users_filter: list[UserType] = strawchemy.update(UserPartial, UserFilter)
        update_users_restricted: list[UserType] = strawchemy.update(
            UserPartial, UserFilter, filter_statement=lambda _: select(User).where(User.id == 2)
        )
        update_users_restricted_join: list[UserType] = strawchemy.update(
            UserPartial,
            UserFilter,
            filter_statement=lambda _: select(User).join(User.departments).where(Department.name == "Sales"),
        )
        update_users_restricted_limit: list[UserType] = strawchemy.update(
            UserPartial,
            UserFilter,
            filter_statement=lambda _: select(User).where(User.id > 1).order_by(User.id).limit(1),
        )
        update_users_restricted_subquery: list[UserType] = strawchemy.update(
            UserPartial,
            UserFilter,
            filter_statement=lambda _: select(User).where(User.id.in_(select(User.id).where(User.id == 2))),
        )
        update_users_restricted_by_name: list[UserType] = strawchemy.update(
            UserPartial, UserFilter, filter_statement=lambda _: select(User).where(User.name == "Bob")
        )
        delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def user_rows() -> RawRecordData:
    return _USERS


@pytest.fixture
def user_department_rows() -> RawRecordData:
    return _USER_DEPARTMENTS


@pytest.fixture
def seed_insert_statements(user_rows: RawRecordData, user_department_rows: RawRecordData) -> list[Insert]:
    return [
        insert(Group).values(_GROUPS),
        insert(Topic).values(_TOPICS),
        insert(Color).values(_COLORS),
        insert(Fruit).values(_FRUITS),
        insert(FruitFarm).values(_FARMS),
        insert(User).values(user_rows),
        insert(Department).values(_DEPARTMENTS),
        insert(UserDepartmentJoinTable).values(user_department_rows),
    ]


@pytest.mark.snapshot
async def test_update_by_filter(
    any_async_query: AnyQueryExecutor,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == [
        {
            "id": to_graphql_representation(_COLORS[0]["id"], "output"),
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
    any_async_query: AnyQueryExecutor,
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
                    name: { eq: "unknown" }
                }
            ) {
                id
                name
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == []

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update color name
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch id + name
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.snapshot
@pytest.mark.parametrize(
    ("dto_filter", "updated_names"),
    [
        pytest.param('{ color: { name: { eq: "Red" } } }', ["Apple", "Cherry"], id="relation"),
        pytest.param(
            '{ _and: [{ sweetness: { gt: 5 } }, { color: { name: { eq: "Red" } } }] }',
            ["Cherry"],
            id="column-and-relation",
        ),
    ],
)
async def test_update_by_filter_on_to_one_relation(
    dto_filter: str,
    updated_names: list[str],
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that an update filtered on a to-one relation updates only the rows whose relation matches."""
    query = f"""
        mutation {{
            updateFruitsFilter(data: {{ sweetness: 42 }}, filter: {dto_filter}) {{
                id
                sweetness
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    updated_ids = [fruit["id"] for fruit in _FRUITS if fruit["name"] in updated_names]
    assert sorted(result.data["updateFruitsFilter"], key=lambda fruit: fruit["id"]) == [
        {"id": to_graphql_representation(fruit_id, "output"), "sweetness": 42} for fruit_id in updated_ids
    ]
    query_tracker.assert_statements(1, "update", sql_snapshot)

    result = await maybe_async(any_async_query("{ fruits(filter: { sweetness: { eq: 42 } }) { id } }"))
    assert not result.errors
    assert result.data
    assert sorted(fruit["id"] for fruit in result.data["fruits"]) == [
        to_graphql_representation(fruit_id, "output") for fruit_id in updated_ids
    ]


@pytest.mark.snapshot
@pytest.mark.parametrize(
    ("dto_filter", "color_index"),
    [
        pytest.param('{ fruits: { name: { in: ["Apple", "Cherry"] } } }', 0, id="relation"),
        pytest.param("{ fruitsAggregate: { count: { arguments: [id], predicate: { gt: 2 } } } }", 1, id="aggregation"),
        pytest.param(
            '{ name: { eq: "Orange" }, fruitsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }',
            2,
            id="column-and-aggregation",
        ),
    ],
)
async def test_update_by_filter_on_to_many_relation(
    dto_filter: str,
    color_index: int,
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that an update filtered on a to-many relation updates each matching row once, and only those."""
    query = f"""
        mutation {{
            updateColorsFilter(data: {{ name: "updated color" }}, filter: {dto_filter}) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    color_id = to_graphql_representation(_COLORS[color_index]["id"], "output")
    assert result.data["updateColorsFilter"] == [{"id": color_id, "name": "updated color"}]
    query_tracker.assert_statements(1, "update", sql_snapshot)

    result = await maybe_async(any_async_query('{ colors(filter: { name: { eq: "updated color" } }) { id } }'))
    assert not result.errors
    assert result.data
    assert result.data["colors"] == [{"id": color_id}]


@pytest.mark.snapshot
@pytest.mark.parametrize(
    ("dto_filter", "updated_names"),
    [
        pytest.param("{ departments: { name: { isNull: true } } }", [], id="to-many-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { name: { isNull: true } } }', [], id="column-and-to-many-null"
        ),
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
        pytest.param("{ group: { name: { isNull: true } } }", [], id="to-one-null"),
        pytest.param('{ name: { neq: "Zed" }, group: { name: { isNull: true } } }', [], id="column-and-to-one-null"),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { isNull: true } } }] }', ["Bob"], id="or-to-one-null"
        ),
        pytest.param(
            '{ name: { neq: "Zed" }, _not: { group: { name: { isNull: true } } } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="column-and-not-to-one-null",
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
        pytest.param('{ _not: { departments: { name: { eq: "IT" } } } }', ["Bob", "Tango"], id="not-to-many"),
        pytest.param(
            '{ _not: { departments: { users: { name: { eq: "Alice" } } } } }', ["Bob", "Tango"], id="not-nested-to-many"
        ),
        pytest.param(
            '{ name: { neq: "Tango" }, _not: { departments: { name: { eq: "IT" } } } }',
            ["Bob"],
            id="column-and-not-to-many",
        ),
        pytest.param(
            '{ departments: { _not: { users: { name: { eq: "Alice" } } } } }',
            ["Bob", "Charlie"],
            id="to-many-not-nested-to-many",
        ),
        pytest.param("{ group: { name: {} } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-empty"),
        pytest.param("{ departments: { name: {} } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many-empty"),
        pytest.param("{ _not: { departments: {} } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-to-many-empty"),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: {} } } }",
            ["Alice", "Bob", "Charlie", "Tango"],
            id="aggregation-empty",
        ),
        pytest.param(
            '{ _or: [{ departments: { name: {} } }, { name: { eq: "Bob" } }] }', ["Bob"], id="or-to-many-empty"
        ),
        pytest.param("{ group: null }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-null-field"),
        pytest.param("{ departments: null }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many-null-field"),
        pytest.param(
            "{ departmentsAggregate: { count: null } }",
            ["Alice", "Bob", "Charlie", "Tango"],
            id="aggregation-null-field",
        ),
        pytest.param('{ _not: null, name: { eq: "Bob" } }', ["Bob"], id="not-null-field"),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: null, predicate: { gt: 0 } } } }",
            ["Alice", "Bob", "Charlie"],
            id="aggregation-arguments-null-field",
        ),
        pytest.param('{ _or: [{ departments: null }, { name: { eq: "Bob" } }] }', ["Bob"], id="or-to-many-null-field"),
        pytest.param(
            '{ _and: [{ departments: { name: { eq: "IT" } } }, { departments: { name: { eq: "Platform" } } }] }',
            ["Charlie"],
            id="and-same-to-many",
        ),
        pytest.param(
            '{ _not: { _and: [{ departments: { name: { eq: "IT" } } }, '
            '{ departments: { name: { eq: "Platform" } } }] } }',
            ["Alice", "Bob", "Tango"],
            id="not-and-same-to-many",
        ),
    ],
)
async def test_update_users_by_split_filter(
    dto_filter: str,
    updated_names: list[str],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that an update split between the WHERE and an EXISTS subquery updates and returns the same rows."""
    query = f"""
        mutation {{
            updateUsersFilter(data: {{ name: "updated" }}, filter: {dto_filter}) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    updated_ids = sorted(user["id"] for user in _USERS if user["name"] in updated_names)
    assert sorted(result.data["updateUsersFilter"], key=lambda user: user["id"]) == [
        {"id": user_id, "name": "updated"} for user_id in updated_ids
    ]
    query_tracker.assert_statements(1, "update", sql_snapshot)

    result = await maybe_async(any_query('{ users(filter: { name: { eq: "updated" } }) { id } }'))
    assert not result.errors
    assert result.data
    assert sorted(user["id"] for user in result.data["users"]) == updated_ids


@pytest.mark.parametrize(
    ("dto_filter", "updated_names"),
    [
        pytest.param("{ name: { in: [] } }", [], id="in"),
        pytest.param("{ bio: { nin: [] } }", ["Alice", "Bob", "Charlie", "Tango"], id="nin"),
        pytest.param(
            "{ departments: { name: { in: [] } } }",
            [],
            id="to-many-in",
        ),
        pytest.param("{ bio: { eq: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="eq-null"),
        pytest.param(
            "{ _not: { bio: { isNull: null, gt: null } } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-null"
        ),
        pytest.param("{ group: { name: { neq: null } } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-null"),
    ],
)
async def test_update_users_by_empty_list_filter(
    dto_filter: str, updated_names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    query = f"""
        mutation {{
            updateUsersFilter(data: {{ name: "updated" }}, filter: {dto_filter}) {{
                id
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    updated_ids = sorted(user["id"] for user in _USERS if user["name"] in updated_names)
    assert sorted(user["id"] for user in result.data["updateUsersFilter"]) == updated_ids

    result = await maybe_async(any_async_query('{ users(filter: { name: { eq: "updated" } }) { id } }'))
    assert not result.errors
    assert result.data
    assert sorted(user["id"] for user in result.data["users"]) == updated_ids


@pytest.mark.snapshot
async def test_update_with_to_one_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(_FRUITS[0]["id"], "input")
    # Use a different color to test the update
    color_id_gql = to_graphql_representation(_COLORS[1]["id"], "input")
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
        "id": to_graphql_representation(_FRUITS[0]["id"], "output"),
        "name": "updated fruit name",
        "color": {"id": to_graphql_representation(_COLORS[1]["id"], "output")},
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_set_null(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting a to-one relationship."""
    fruit_id_gql = to_graphql_representation(_FRUITS[0]["id"], "input")
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
        "id": to_graphql_representation(_FRUITS[0]["id"], "output"),
        "name": "updated fruit name",
        "color": None,
    }

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + color


@pytest.mark.snapshot
async def test_update_with_to_one_create(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating a new related record for a to-one relationship."""
    fruit_id_gql = to_graphql_representation(_FRUITS[0]["id"], "input")
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateFruit"] == {
        "id": to_graphql_representation(_FRUITS[0]["id"], "output"),
        "name": "updated fruit name 2",
        "color": {"name": "newly created color during update"},
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new color
    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update fruit's color_id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated fruit + new color


@pytest.mark.snapshot
async def test_update_with_to_one_create_and_nested_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a relationship."""
    user_id_gql = to_graphql_representation(_USERS[0]["id"], "input")
    # Use a different topic to test the update/create
    topic_id_gql = to_graphql_representation(_TOPICS[1]["id"], "input")
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
        "id": to_graphql_representation(_USERS[0]["id"], "output"),
        "name": "Updated Bob",
        "group": {
            "name": "new group during update",
            "topics": [{"id": to_graphql_representation(_TOPICS[1]["id"], "output")}],
        },
    }

    query_tracker.assert_statements(1, "insert", sql_snapshot)  # Insert new group
    query_tracker.assert_statements(2, "update", sql_snapshot)  # Update user's group_id and topic's group id
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated user + new group + topic


@pytest.mark.snapshot
async def test_update_with_to_many_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(_COLORS[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(_FRUITS[1]["id"], "input")
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
        "id": to_graphql_representation(_COLORS[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [{"id": to_graphql_representation(_FRUITS[1]["id"], "output")}],
    }

    # 1. Disconnect previous fruits
    # 2. Update specified fruit's color_id
    # 3. Update color's name
    query_tracker.assert_statements(3, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_remove(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(_COLORS[0]["id"], "input")
    # Remove the existing fruits
    fruit_ids_gql = [
        to_graphql_representation(fruit["id"], "input") for fruit in _FRUITS if fruit["color_id"] == _COLORS[0]["id"]
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(_COLORS[0]["id"], "output"),
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
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
    dialect: SupportedDialect,
) -> None:
    """Tests updating a record and creating new related records for a to-many relationship."""
    color_id = _COLORS[0]["id"]
    color_id_gql = to_graphql_representation(color_id, "input")
    query = f"""
        mutation {{
            updateColor(
                data: {{
                    id: {color_id_gql},
                    name: "updated color name 2",
                    fruits: {{
                        create: [
                            {{ name: "new fruit 3 during update", sweetness: 1, waterPercent: 0.7 }},
                            {{ name: "new fruit 4 during update", sweetness: 1, waterPercent: 0.6 }}
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    # The order might vary, sort for assertion stability
    fruits_data = sorted(result.data["updateColor"]["fruits"], key=lambda x: x["name"])
    assert result.data["updateColor"]["id"] == to_graphql_representation(color_id, "output")
    assert result.data["updateColor"]["name"] == "updated color name 2"
    assert fruits_data == [
        *[{"name": fruit["name"]} for fruit in _FRUITS if fruit["color_id"] == color_id],
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
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating a nested related record which itself sets a to-many relationship."""
    color_id = _COLORS[0]["id"]
    color_id_gql = to_graphql_representation(color_id, "input")
    # Use a different farm
    farm_id = _FARMS[-1]["id"]
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    expected_fruits = [
        # Existing fruits
        *[
            {
                "name": fruit["name"],
                "farms": [
                    {"id": to_graphql_representation(farm["id"], "output")}
                    for farm in _FARMS
                    if farm["fruit_id"] == fruit["id"]
                ],
            }
            for fruit in _FRUITS
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
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(_COLORS[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(_FRUITS[1]["id"], "input")
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"] == {
        "id": to_graphql_representation(_COLORS[0]["id"], "output"),
        "name": "updated color name",
        "fruits": [
            {"id": to_graphql_representation(_FRUITS[0]["id"], "output")},
            {"id": to_graphql_representation(_FRUITS[1]["id"], "output")},
        ],
    }

    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_to_many_add_and_create(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and setting (replacing) a to-many relationship."""
    color_id_gql = to_graphql_representation(_COLORS[0]["id"], "input")
    # Use a different fruit to test the update
    fruit_id_gql = to_graphql_representation(_FRUITS[1]["id"], "input")
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert result.data["updateColor"]["id"] == to_graphql_representation(_COLORS[0]["id"], "output")
    assert result.data["updateColor"]["name"] == "updated color name"
    expected = [
        {"name": to_graphql_representation(_FRUITS[0]["name"], "output")},
        {"name": "new fruit 3 during update"},
        {"name": to_graphql_representation(_FRUITS[1]["name"], "output")},
    ]
    for fruit in expected:
        assert fruit in result.data["updateColor"]["fruits"]

    query_tracker.assert_statements(1, "insert", sql_snapshot)
    # 1. Update specified fruit's color_id
    # 2. Update color's name
    query_tracker.assert_statements(2, "update", sql_snapshot)
    # Fetch updated color + fruit
    query_tracker.assert_statements(1, "select", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_nested_mixed_relations_create(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating a record and creating multiple nested relations with different structures."""
    color_id = _COLORS[0]["id"]
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
                                waterPercent: 0.7,
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
    result = await maybe_async(any_async_query(query))
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
                    {"name": to_graphql_representation(farm["name"], "output")}
                    for farm in _FARMS
                    if farm["fruit_id"] == fruit["id"]
                ],
                "product": None,
            }
            for fruit in _FRUITS
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
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Tests updating multiple records in a single mutation."""
    color_id1_gql = to_graphql_representation(_COLORS[0]["id"], "input")
    color_id2_gql = to_graphql_representation(_COLORS[1]["id"], "input")
    query = f"""
        mutation {{
            updateColors(
                data: [
                    {{ id: {color_id1_gql}, name: "batch updated color 1" }},
                    {{ id: {color_id2_gql}, name: "batch updated color 2" }}
                ]
            ) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    # Order might not be guaranteed, sort by ID
    updated_colors = sorted(result.data["updateColors"], key=lambda x: x["id"])
    expected_colors = sorted(
        [
            {"id": to_graphql_representation(_COLORS[0]["id"], "output"), "name": "batch updated color 1"},
            {"id": to_graphql_representation(_COLORS[1]["id"], "output"), "name": "batch updated color 2"},
        ],
        key=lambda x: x["id"],
    )
    assert updated_colors == expected_colors

    query_tracker.assert_statements(1, "update", sql_snapshot)  # Update colors in a single query
    query_tracker.assert_statements(1, "select", sql_snapshot)  # Fetch updated records


@pytest.mark.snapshot
async def test_update_no_init_defaults(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query(
            f"""
            mutation {{
                updateUser(data: {{ id: {_USERS[3]["id"]}, name: "Jeanne" }}) {{
                    name
                    bio
                }}
            }}
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["updateUser"] == {"name": "Jeanne", "bio": _USERS[3]["bio"]}

    query_tracker.assert_statements(1, "update", sql_snapshot)


@pytest.mark.snapshot
async def test_update_with_secondary_table_set(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    query = f"""
    mutation {{
        updateUser(data: {{ id: {_USERS[1]["id"]}, departments: {{ set: [ {{ id: 1 }} ] }} }}) {{
            name
            departments {{
                id
                name
            }}
        }}
    }}
    """

    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data

    assert result.data["updateUser"] == {"name": "Bob", "departments": [{"id": 1, "name": "IT"}]}

    assert query_tracker.query_count == 3
    # Insert new m2m relation
    query_tracker.assert_statements(1, "insert", sql_snapshot)
    # Delete old ones
    query_tracker.assert_statements(1, "delete", sql_snapshot)
    # Select result
    query_tracker.assert_statements(1, "select", sql_snapshot)


async def test_update_and_delete_filter_without_returning(
    any_query: AnyQueryExecutor,
    any_session: AnySession,
    query_tracker: QueryTracker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a dialect without UPDATE/DELETE RETURNING, filtered mutations select the affected rows before running."""
    dialect = any_session.get_bind().dialect
    monkeypatch.setattr(dialect, "update_returning", False)
    monkeypatch.setattr(dialect, "delete_returning", False)

    result = await maybe_async(
        any_query('mutation { updateColorsFilter(data: { name: "updated" }, filter: { name: { eq: "Red" } }) { id } }')
    )
    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == [{"id": to_graphql_representation(_COLORS[0]["id"], "output")}]

    result = await maybe_async(any_query('mutation { deleteUsersFilter(filter: { name: { eq: "Alice" } }) { id } }'))
    assert not result.errors
    assert result.data
    alice = next(user for user in _USERS if user["name"] == "Alice")
    assert result.data["deleteUsersFilter"] == [{"id": to_graphql_representation(alice["id"], "output")}]

    assert query_tracker.filter("update").query_count == 1
    assert query_tracker.filter("delete").query_count == 1
    assert all("RETURNING" not in query.statement_str for query in query_tracker)


@pytest.mark.parametrize(
    ("first", "second", "above", "updated_names"),
    [
        pytest.param("Banana", "Lemon", 2, ["Yellow"], id="count-passes"),
        pytest.param("Banana", "Lemon", 3, [], id="count-fails"),
        pytest.param("Apple", "Lemon", 1, [], id="fruits-of-two-colors"),
    ],
)
async def test_update_filter_and_branch_counting_a_shared_to_many(
    first: str,
    second: str,
    above: int,
    updated_names: list[str],
    any_async_query: AnyQueryExecutor,
) -> None:
    """An update filtered on a fruit and an ``_and`` branch counting fruits and testing another updates the matches."""
    count = f"fruitsAggregate: {{ count: {{ predicate: {{ gt: {above} }} }} }}"
    dto_filter = f'{{ fruits: {{ name: {{ eq: "{first}" }} }}, _and: [{{ {count}, fruits: {{ name: {{ eq: "{second}" }} }} }}] }}'

    result = await maybe_async(
        any_async_query(
            f'mutation {{ updateColorsFilter(data: {{ name: "updated" }}, filter: {dto_filter}) {{ id }} }}'
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["updateColorsFilter"] == [
        {"id": to_graphql_representation(color["id"], "output")} for color in _COLORS if color["name"] in updated_names
    ]


@pytest.mark.parametrize(
    ("user_rows", "user_department_rows"),
    [
        pytest.param(
            [
                {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
                {"id": 2, "name": "Bob", "group_id": 1, "bio": None},
                {"id": 3, "name": "Charlie", "group_id": 2, "bio": None},
                {"id": 4, "name": "Dave", "group_id": 1, "bio": None},
                {"id": 5, "name": "Eve", "group_id": None, "bio": None},
            ],
            [
                {"user_id": 1, "department_id": 1},
                {"user_id": 2, "department_id": 2},
                {"user_id": 3, "department_id": 1},
                {"user_id": 4, "department_id": 1},
                {"user_id": 4, "department_id": 3},
                {"user_id": 5, "department_id": 3},
            ],
            id="dave-in-two-departments",
        )
    ],
)
async def test_update_filter_counting_the_table_next_to_two_to_many_paths(
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
    user_department_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """An update filtered on a department, a topic of the group and a department count updates the users passing all."""
    dto_filter = (
        '{ departments: { name: { eq: "IT" } }, group: { topics: { name: { eq: "Hello!" } } }, '
        "departmentsAggregate: { count: { predicate: { gt: 1 } } } }"
    )

    result = await maybe_async(
        any_async_query(f'mutation {{ updateUsersFilter(data: {{ name: "updated" }}, filter: {dto_filter}) {{ id }} }}')
    )

    assert not result.errors
    assert result.data
    assert result.data["updateUsersFilter"] == [{"id": to_graphql_representation(4, "output")}]


@pytest.mark.parametrize(
    ("field", "dto_filter", "updated_names"),
    [
        pytest.param("updateUsersRestricted", ', filter: { name: { neq: "zzz" } }', ["Bob"], id="where"),
        pytest.param("updateUsersRestricted", "", ["Bob"], id="where-no-filter"),
        pytest.param("updateUsersRestricted", ", filter: {}", ["Bob"], id="where-empty-filter"),
        pytest.param("updateUsersRestricted", ', filter: { name: { eq: "Alice" } }', [], id="where-disjoint-filter"),
        pytest.param("updateUsersRestrictedJoin", ', filter: { name: { neq: "zzz" } }', ["Bob"], id="join"),
        pytest.param("updateUsersRestrictedJoin", "", ["Bob"], id="join-no-filter"),
        pytest.param("updateUsersRestrictedJoin", ', filter: { name: { eq: "Alice" } }', [], id="join-disjoint-filter"),
        pytest.param("updateUsersRestrictedLimit", ', filter: { name: { neq: "zzz" } }', ["Bob"], id="limit"),
        pytest.param("updateUsersRestrictedLimit", "", ["Bob"], id="limit-no-filter"),
        pytest.param("updateUsersRestrictedSubquery", ', filter: { name: { neq: "zzz" } }', ["Bob"], id="subquery"),
        pytest.param("updateUsersRestrictedSubquery", ", filter: {}", ["Bob"], id="subquery-empty-filter"),
        pytest.param("updateUsersRestrictedByName", ", filter: {}", ["Bob"], id="moved-out"),
        pytest.param("updateUsersRestrictedByName", "", ["Bob"], id="moved-out-no-filter"),
    ],
)
async def test_update_restricted_by_repository_statement(
    field: str, dto_filter: str, updated_names: list[str], any_query: AnyQueryExecutor
) -> None:
    """An update whose repository statement keeps only Bob updates at most Bob, whatever the statement and filter."""
    result = await maybe_async(any_query(f'mutation {{ {field}(data: {{ name: "Updated" }}{dto_filter}) {{ name }} }}'))
    assert not result.errors
    assert result.data
    assert result.data[field] == [{"name": "Updated"} for _ in updated_names]

    result = await maybe_async(any_query("{ users { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["users"]) == sorted(
        "Updated" if user["name"] in updated_names else user["name"] for user in _USERS
    )
