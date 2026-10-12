from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert, select
from strawberry.types import get_object_definition

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Color, Department, Fruit, User, UserDepartment, UserDepartmentJoinTable
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [
    {"id": 1, "name": "Red"},
    {"id": 2, "name": "Yellow"},
    {"id": 3, "name": "Green"},
    {"id": 4, "name": "Pink"},
]
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
    {
        "id": 3,
        "name": "Banana",
        "sweetness": 2,
        "water_percent": 0.75,
        "best_time_to_pick": time(hour=17, minute=15),
        "color_id": 2,
    },
]
_USERS: list[dict[str, Any]] = [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 3, "name": "Charlie"},
    {"id": 4, "name": "Tango"},
]
_DEPARTMENTS: list[dict[str, Any]] = [
    {"id": 1, "name": "IT"},
    {"id": 2, "name": "Sales"},
    {"id": 3, "name": "Platform"},
]
_USER_DEPARTMENTS: list[dict[str, Any]] = [
    {"user_id": 1, "department_id": 1},
    {"user_id": 2, "department_id": 2},
    {"user_id": 3, "department_id": 3},
    {"user_id": 3, "department_id": 1},
]
_VISIBLE_COLOR_NAMES = ["Red", "Green", "Pink"]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "color"], override=True)
    class FruitType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], override=True)
    class ColorType: ...

    @strawchemy.type(User, include=["id", "name", "greeting", "departments"])
    class UserType: ...

    @strawchemy.type(UserDepartment, include=["user_id", "department_id"])
    class UserDepartmentType: ...

    @strawchemy.order(Color, include=["id", "name"])
    class ColorOrder: ...

    @strawchemy.distinct_on(Color, include=["name"])
    class ColorDistinctOn: ...

    @strawberry.type
    class Query:
        user: UserType = strawchemy.field()
        user_by_pk: UserType = strawchemy.field(id_field_name="pk")
        user_department: UserDepartmentType = strawchemy.field()
        users: list[UserType] = strawchemy.field()
        fruits: list[FruitType] = strawchemy.field()
        colors: list[ColorType] = strawchemy.field()
        colors_filtered: list[ColorType] = strawchemy.field(
            filter_statement=lambda _: select(Color).where(Color.name == "Red")
        )
        colors_filtered_paginated: list[ColorType] = strawchemy.field(
            order_by_input=ColorOrder,
            pagination=True,
            filter_statement=lambda _: select(Color).where(Color.name.in_(_VISIBLE_COLOR_NAMES)),
        )
        colors_filtered_distinct: list[ColorType] = strawchemy.field(
            distinct_on=ColorDistinctOn,
            order_by_input=ColorOrder,
            pagination=True,
            filter_statement=lambda _: select(Color).where(Color.name.in_(_VISIBLE_COLOR_NAMES)),
        )

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Color).values(_COLORS),
        insert(Fruit).values(_FRUITS),
        insert(User).values(_USERS),
        insert(Department).values(_DEPARTMENTS),
        insert(UserDepartmentJoinTable).values(_USER_DEPARTMENTS),
    ]


async def test_single(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    name
            }
            }
            """,
            {"id": _USERS[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"name": _USERS[0]["name"]}


async def test_single_with_custom_id_field_name(any_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_query(
            """
            query GetUser($pk: Int!) {
                userByPk(pk: $pk) {
                    name
                }
            }
            """,
            {"pk": _USERS[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["userByPk"] == {"name": _USERS[0]["name"]}


async def test_single_with_composite_primary_key(any_query: AnyQueryExecutor) -> None:
    expected = _USER_DEPARTMENTS[3]
    result = await maybe_async(
        any_query(
            """
            query GetUserDepartment($userId: Int!, $departmentId: Int!) {
                userDepartment(userId: $userId, departmentId: $departmentId) {
                    userId
                    departmentId
                }
            }
            """,
            {"userId": expected["user_id"], "departmentId": expected["department_id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["userDepartment"] == {"userId": expected["user_id"], "departmentId": expected["department_id"]}


async def test_typename_do_not_fail(any_async_query: AnyQueryExecutor, schema: SchemaTypes) -> None:
    result = await maybe_async(
        any_async_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    __typename
            }
            }
            """,
            {"id": _USERS[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    user_field = next(
        field
        for field in get_object_definition(schema.async_operations.query, strict=True).fields
        if field.name == "user"
    )
    assert result.data["user"] == {"__typename": get_object_definition(user_field.type, strict=True).name}


async def test_many(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query("{ users { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in _USERS]


async def test_root_fields_share_async_session(any_async_query: AnyQueryExecutor) -> None:
    """Test that sibling root fields resolved concurrently on one async session all succeed."""
    result = await maybe_async(any_async_query("{ users { name } colors { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in _USERS]
    assert result.data["colors"] == [{"name": color["name"]} for color in _COLORS]


async def test_relation(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query("{ fruits { color { id } } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruits"] == [{"color": {"id": fruit["color_id"]}} for fruit in _FRUITS]


async def test_list_relation(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query("{ colors { id fruits { name id } } }"))

    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        assert len(color["fruits"]) == len([f for f in _FRUITS if f["color_id"] == color["id"]])
        for fruit in color["fruits"]:
            expected = next(f for f in _FRUITS if f["id"] == fruit["id"])
            assert fruit == {"name": expected["name"], "id": expected["id"]}


async def test_repeated_root_field_merges_selections(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a root field selected twice under one response key loads the columns of both selections."""
    result = await maybe_async(any_async_query("{ colors { id } colors { name } }"))

    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert sorted(result.data["colors"], key=lambda color: color["id"]) == _COLORS


async def test_column_property(any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(
        any_async_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    greeting
            }
            }
            """,
            {"id": _USERS[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"greeting": f"Hello, {_USERS[0]['name']}"}


@pytest.mark.snapshot
async def test_only_queried_columns_included_in_select(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    await maybe_async(any_async_query("{ colors { name fruits { name id } } }"))
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_filtered_statement(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query("{ colorsFiltered { name } }"))

    assert not result.errors
    assert result.data
    assert len(result.data["colorsFiltered"]) == 1
    assert result.data["colorsFiltered"][0]["name"] == "Red"

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("limit", "offset", "expected"),
    [
        pytest.param(1, 0, ["Red"], id="first-page"),
        pytest.param(1, 1, ["Green"], id="second-page"),
        pytest.param(2, 0, ["Red", "Green"], id="full-set"),
    ],
)
async def test_filter_statement_pagination(
    any_async_query: AnyQueryExecutor, limit: int, offset: int, expected: list[str]
) -> None:
    """filter_statement must scope rows BEFORE limit/offset."""
    query = f"{{ colorsFilteredPaginated(limit: {limit}, offset: {offset}, orderBy: [{{id: ASC}}]) {{ name }} }}"
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert [c["name"] for c in result.data["colorsFilteredPaginated"]] == expected


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        # Visible names sorted ASC: Green, Pink, Red
        pytest.param(0, ["Green"], id="first"),
        pytest.param(1, ["Pink"], id="second"),
        pytest.param(2, ["Red"], id="third"),
    ],
)
async def test_filter_statement_distinct_pagination(
    any_async_query: AnyQueryExecutor, offset: int, expected: list[str]
) -> None:
    """filter_statement must scope rows before DISTINCT ON ranking and pagination."""
    query = (
        f"{{ colorsFilteredDistinct(distinctOn: [name], orderBy: [{{name: ASC}}], limit: 1, offset: {offset})"
        " { name } }"
    )
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert [c["name"] for c in result.data["colorsFilteredDistinct"]] == expected


@pytest.mark.snapshot
async def test_secondary_table_relationships(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    result = await maybe_async(any_async_query("{ users { id departments { id name } } }"))

    assert not result.errors
    assert result.data

    assert len(result.data["users"]) == len(_USERS)
    assert result.data["users"] == [
        {"id": 1, "departments": [{"id": 1, "name": "IT"}]},
        {"id": 2, "departments": [{"id": 2, "name": "Sales"}]},
        {"id": 3, "departments": [{"id": 1, "name": "IT"}, {"id": 3, "name": "Platform"}]},
        {"id": 4, "departments": []},
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_filter_statement_pagination_sql(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query("{ colorsFilteredPaginated(limit: 1, offset: 1, orderBy: [{id: ASC}]) { name } }")
    )
    assert not result.errors
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
