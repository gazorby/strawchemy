from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import Department, User, UserDepartmentJoinTable
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Charlie belongs to two departments and Tango to none. The `filtered_departments` predicates exclude Bob and IT, so
# its counts differ from those of `departments` for every user but Tango.
_USERS: RawRecordData = [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 3, "name": "Charlie"},
    {"id": 4, "name": "Tango"},
]
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
    @strawchemy.type(Department, include=["id", "users"], scope="schema")
    class DepartmentType: ...

    @strawchemy.type(User, include=["id", "departments", "filtered_departments"], scope="schema")
    class UserType: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field()

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(User).values(_USERS),
        insert(Department).values(_DEPARTMENTS),
        insert(UserDepartmentJoinTable).values(_USER_DEPARTMENTS),
    ]


async def test_count_aggregation_many_to_many(any_async_query: AnyQueryExecutor) -> None:
    """Test that a many-to-many count matches the number of join-table rows of each user."""
    result = await maybe_async(
        any_async_query(
            """
            {
                users {
                    id
                    departmentsAggregate { count }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    departments_per_user = Counter(link["user_id"] for link in _USER_DEPARTMENTS)
    actual = {user["id"]: user["departmentsAggregate"]["count"] for user in result.data["users"]}
    assert actual == {user["id"]: departments_per_user[user["id"]] for user in _USERS}


async def test_count_aggregation_many_to_many_join_predicates(any_async_query: AnyQueryExecutor) -> None:
    """Test that a many-to-many count honours the relationship primaryjoin and secondaryjoin predicates."""
    result = await maybe_async(
        any_async_query(
            """
            {
                users {
                    id
                    filteredDepartmentsAggregate { count }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    user_names = {user["id"]: user["name"] for user in _USERS}
    department_names = {department["id"]: department["name"] for department in _DEPARTMENTS}
    joined = Counter(
        link["user_id"]
        for link in _USER_DEPARTMENTS
        if user_names[link["user_id"]] != "Bob" and department_names[link["department_id"]] != "IT"
    )
    actual = {user["id"]: user["filteredDepartmentsAggregate"]["count"] for user in result.data["users"]}
    assert actual == {user["id"]: joined[user["id"]] for user in _USERS}


async def test_count_aggregation_many_to_many_nested(any_async_query: AnyQueryExecutor) -> None:
    """Test that a nested many-to-many count matches the number of users of each department."""
    result = await maybe_async(
        any_async_query(
            """
            {
                users {
                    id
                    departments {
                        id
                        usersAggregate { count }
                    }
                }
            }
            """
        )
    )
    assert not result.errors
    assert result.data
    users_per_department = Counter(link["department_id"] for link in _USER_DEPARTMENTS)
    actual = {
        (user["id"], department["id"]): department["usersAggregate"]["count"]
        for user in result.data["users"]
        for department in user["departments"]
    }
    assert actual == {
        (link["user_id"], link["department_id"]): users_per_department[link["department_id"]]
        for link in _USER_DEPARTMENTS
    }
