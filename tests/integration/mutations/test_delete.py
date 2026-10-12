from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, insert, select

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Department, Group, Topic, User, UserDepartment, UserDepartmentJoinTable
from tests.integration.typing import RawRecordData
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_GROUPS: RawRecordData = [{"id": 1, "name": "Group 1"}]
# Alice's group holds a topic, so `topicsAggregate` counts tell it apart from no group.
_TOPICS: RawRecordData = [{"id": 1, "name": "Hello!", "group_id": 1}]
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


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(User, include=["id", "name", "group"])
    class UserType: ...

    # The include list also filters the count arguments of the aggregations below it: cases count on `id`.
    @strawchemy.filter(User, include=["id", "name", "bio", "group", "departments"])
    class UserFilter: ...

    @strawchemy.type(UserDepartment, include="all")
    class UserDepartmentType: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field()
        user_departments: list[UserDepartmentType] = strawchemy.field()

    @strawberry.type
    class Mutation:
        delete_users: list[UserType] = strawchemy.delete()
        delete_users_filter: list[UserType] = strawchemy.delete(UserFilter)
        delete_users_restricted: list[UserType] = strawchemy.delete(
            UserFilter, filter_statement=lambda _: select(User).where(User.id == 2)
        )
        delete_users_restricted_join: list[UserType] = strawchemy.delete(
            UserFilter, filter_statement=lambda _: select(User).join(User.departments).where(Department.name == "Sales")
        )
        delete_users_restricted_limit: list[UserType] = strawchemy.delete(
            UserFilter, filter_statement=lambda _: select(User).where(User.id > 1).order_by(User.id).limit(1)
        )
        delete_users_restricted_subquery: list[UserType] = strawchemy.delete(
            UserFilter,
            filter_statement=lambda _: select(User).where(User.id.in_(select(User.id).where(User.name == "Bob"))),
        )
        delete_users_restricted_without_filter: list[UserType] = strawchemy.delete(
            filter_statement=lambda _: select(User).where(User.id == 2)
        )
        delete_user_departments_restricted_limit: list[UserDepartmentType] = strawchemy.delete(
            filter_statement=lambda _: select(UserDepartment).order_by(*UserDepartmentJoinTable.primary_key).limit(1)
        )

    return Operations(query=Query, mutation=Mutation)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Group).values(_GROUPS),
        insert(Topic).values(_TOPICS),
        insert(User).values(_USERS),
        insert(Department).values(_DEPARTMENTS),
        insert(UserDepartmentJoinTable).values(_USER_DEPARTMENTS),
    ]


@pytest.mark.parametrize(
    ("dto_filter", "deleted_names"),
    [
        pytest.param("{ name: { in: [] } }", [], id="in"),
        pytest.param("{ _not: { bio: { in: [] } } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-in"),
        pytest.param("{ bio: { isNull: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="is-null-null"),
        pytest.param(
            "{ _not: { name: { like: null, regexp: null } } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-null"
        ),
        pytest.param(
            "{ departments: { name: { eq: null } } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many-null"
        ),
    ],
)
async def test_delete_users_by_empty_list_filter(
    dto_filter: str, deleted_names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(any_async_query(f"mutation {{ deleteUsersFilter(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["deleteUsersFilter"]) == deleted_names

    result = await maybe_async(any_async_query("{ users { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["users"]) == sorted(
        user["name"] for user in _USERS if user["name"] not in deleted_names
    )


@pytest.mark.snapshot
async def test_delete_filter(
    any_async_query: AnyQueryExecutor,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsersFilter"]) == 1
    apple_fruit = next(fruit for fruit in _USERS if fruit["name"] == "Alice")
    assert result.data["deleteUsersFilter"] == [
        {"id": apple_fruit["id"], "name": "Alice", "group": {"name": _GROUPS[0]["name"]}}
    ]

    query_tracker.assert_statements(1, "delete", sql_snapshot)
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)


@pytest.mark.parametrize(
    ("dto_filter", "deleted_names"),
    [
        pytest.param('{ name: { eq: "Alice" } }', ["Alice"], id="name"),
        pytest.param("{ bio: { isNull: false } }", ["Tango"], id="bio"),
    ],
)
async def test_delete_filter_on_unselected_column(
    dto_filter: str, deleted_names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Deleting by a filter on a column the selection does not read returns the ids of the deleted rows."""
    result = await maybe_async(any_async_query(f"mutation {{ deleteUsersFilter(filter: {dto_filter}) {{ id }} }}"))
    assert not result.errors
    assert result.data
    assert result.data["deleteUsersFilter"] == [
        {"id": to_graphql_representation(user["id"], "output")} for user in _USERS if user["name"] in deleted_names
    ]

    result = await maybe_async(any_async_query("{ users { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["users"]) == sorted(
        user["name"] for user in _USERS if user["name"] not in deleted_names
    )


@pytest.mark.parametrize(
    ("field", "arguments", "deleted_names"),
    [
        pytest.param("deleteUsersRestricted", '(filter: { name: { neq: "zzz" } })', ["Bob"], id="where"),
        pytest.param("deleteUsersRestricted", "", ["Bob"], id="where-no-filter"),
        pytest.param("deleteUsersRestricted", "(filter: {})", ["Bob"], id="where-empty-filter"),
        pytest.param("deleteUsersRestricted", '(filter: { name: { eq: "Alice" } })', [], id="where-disjoint-filter"),
        pytest.param("deleteUsersRestrictedJoin", '(filter: { name: { neq: "zzz" } })', ["Bob"], id="join"),
        pytest.param("deleteUsersRestrictedJoin", "", ["Bob"], id="join-no-filter"),
        pytest.param("deleteUsersRestrictedJoin", '(filter: { name: { eq: "Alice" } })', [], id="join-disjoint-filter"),
        pytest.param("deleteUsersRestrictedLimit", '(filter: { name: { neq: "zzz" } })', ["Bob"], id="limit"),
        pytest.param("deleteUsersRestrictedLimit", "", ["Bob"], id="limit-no-filter"),
        pytest.param("deleteUsersRestrictedSubquery", '(filter: { name: { neq: "zzz" } })', ["Bob"], id="subquery"),
        pytest.param("deleteUsersRestrictedSubquery", "(filter: {})", ["Bob"], id="subquery-empty-filter"),
        pytest.param("deleteUsersRestrictedWithoutFilter", "", ["Bob"], id="no-filter-input"),
    ],
)
async def test_delete_restricted_by_repository_statement(
    field: str, arguments: str, deleted_names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """A delete whose repository statement keeps only Bob deletes at most Bob, whatever the statement and filter."""
    result = await maybe_async(any_async_query(f"mutation {{ {field}{arguments} {{ name }} }}"))
    assert not result.errors
    assert result.data
    assert [user["name"] for user in result.data[field]] == deleted_names

    result = await maybe_async(any_async_query("{ users { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["users"]) == sorted(
        user["name"] for user in _USERS if user["name"] not in deleted_names
    )


async def test_delete_restricted_by_repository_statement_on_composite_primary_key(
    any_async_query: AnyQueryExecutor,
) -> None:
    """A delete whose limited repository statement keeps one composite-key row deletes that row alone."""
    result = await maybe_async(
        any_async_query("mutation { deleteUserDepartmentsRestrictedLimit { userId departmentId } }")
    )
    assert not result.errors
    assert result.data
    assert result.data["deleteUserDepartmentsRestrictedLimit"] == [{"userId": 1, "departmentId": 1}]

    result = await maybe_async(any_async_query("{ userDepartments { userId departmentId } }"))
    assert not result.errors
    assert result.data
    assert sorted((row["userId"], row["departmentId"]) for row in result.data["userDepartments"]) == sorted(
        (row["user_id"], row["department_id"]) for row in _USER_DEPARTMENTS[1:]
    )


@pytest.mark.snapshot
@pytest.mark.parametrize(
    ("dto_filter", "deleted_names"),
    [
        pytest.param('{ group: { name: { eq: "Group 1" } } }', ["Alice"], id="to-one"),
        pytest.param('{ departments: { name: { eq: "IT" } } }', ["Alice", "Charlie"], id="to-many"),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { eq: "Group 1" } } }] }',
            ["Alice", "Bob"],
            id="or-column-relation",
        ),
        pytest.param('{ _not: { group: { name: { eq: "Group 1" } } } }', ["Bob", "Charlie", "Tango"], id="not-to-one"),
        pytest.param(
            '{ departments: { users: { name: { eq: "Alice" } } } }', ["Alice", "Charlie"], id="nested-to-many"
        ),
        pytest.param('{ name: { eq: "Bob" } }', ["Bob"], id="column"),
        pytest.param(
            '{ name: { neq: "Alice" }, departments: { name: { eq: "IT" } } }', ["Charlie"], id="column-and-to-many"
        ),
        pytest.param(
            '{ _and: [{ name: { eq: "Alice" } }, { departments: { name: { eq: "IT" } } }] }',
            ["Alice"],
            id="and-column-relation",
        ),
        pytest.param(
            '{ _and: [{ _and: [{ name: { neq: "Alice" } }, { name: { neq: "Bob" } }] }, '
            '{ departments: { name: { in: ["IT", "Sales"] } } }] }',
            ["Charlie"],
            id="nested-and-column-relation",
        ),
        pytest.param(
            '{ name: { neq: "Alice" }, _or: [{ name: { eq: "Bob" } }, { group: { name: { eq: "Group 1" } } }] }',
            ["Bob"],
            id="column-and-or-column-relation",
        ),
        pytest.param(
            '{ _not: { name: { eq: "Bob" } }, departments: { name: { in: ["IT", "Sales"] } } }',
            ["Alice", "Charlie"],
            id="not-column-and-relation",
        ),
        pytest.param(
            '{ name: { neq: "Bob" }, _not: { group: { name: { eq: "Group 1" } } } }',
            ["Charlie", "Tango"],
            id="column-and-not-to-one",
        ),
        pytest.param(
            '{ name: { neq: "Alice" }, departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }',
            ["Charlie"],
            id="column-and-aggregation",
        ),
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
    ],
)
async def test_delete_filter_on_relation(
    dto_filter: str,
    deleted_names: list[str],
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a delete filtered on a relation deletes and returns only the rows whose relation matches."""
    query = f"""
        mutation {{
            deleteUsersFilter(filter: {dto_filter}) {{
                id
                name
            }}
        }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert sorted(result.data["deleteUsersFilter"], key=lambda user: user["id"]) == [
        {"id": user["id"], "name": user["name"]} for user in _USERS if user["name"] in deleted_names
    ]
    query_tracker.assert_statements(1, "delete", sql_snapshot)

    result = await maybe_async(any_query("{ users { name } }"))
    assert not result.errors
    assert result.data
    assert sorted(user["name"] for user in result.data["users"]) == sorted(
        user["name"] for user in _USERS if user["name"] not in deleted_names
    )


@pytest.mark.snapshot
async def test_delete_all(
    any_async_query: AnyQueryExecutor,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["deleteUsers"]) == len(_USERS)
    query_tracker.assert_statements(1, "delete", sql_snapshot)
    if dialect in ("postgresql", "sqlite"):
        query_tracker.assert_statements(1, "select", sql_snapshot)
    else:
        query_tracker.assert_statements(2, "select", sql_snapshot)
