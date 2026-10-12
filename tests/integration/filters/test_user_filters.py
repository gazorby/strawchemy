from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Department, Group, Topic, User, UserDepartmentJoinTable
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

# Group 2 holds no default user: it is the parent of a topic other than "Hello!", and of Charlie in
# test_aggregate_under_one_of_two_to_many_paths.
_GROUPS: RawRecordData = [
    {"id": 1, "name": "Group 1"},
    {"id": 2, "name": "Group 2"},
]
_TOPICS: RawRecordData = [
    {"id": 1, "name": "Hello!", "group_id": 1},
    {"id": 2, "name": "Problems", "group_id": 2},
]
# Only Alice has a group and only Tango has a bio; Tango belongs to no department and Charlie to two.
_USERS: RawRecordData = [
    {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
    {"id": 2, "name": "Bob", "group_id": None, "bio": None},
    {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
    {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
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
_ALL_USERS = sorted(user["name"] for user in _USERS)
_TEXT_OPERATORS = (
    "eq",
    "neq",
    "isNull",
    "in",
    "nin",
    "gt",
    "gte",
    "lt",
    "lte",
    "like",
    "nlike",
    "ilike",
    "nilike",
    "regexp",
    "iregexp",
    "nregexp",
    "inregexp",
    "startswith",
    "endswith",
    "contains",
    "istartswith",
    "iendswith",
    "icontains",
)


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(User, include=["id", "name", "bio"])
    class UserType: ...

    # The include list also filters the count arguments of the aggregations below it: cases count on `id`.
    @strawchemy.filter(User, include=["id", "name", "bio", "group", "departments"])
    class UserFilter: ...

    @strawchemy.distinct_on(User, include=["name"])
    class UserDistinctOn: ...

    @strawberry.type
    class Query:
        users: list[UserType] = strawchemy.field(filter_input=UserFilter, distinct_on=UserDistinctOn)
        users_paginated: list[UserType] = strawchemy.field(filter_input=UserFilter, pagination=True)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def group_rows() -> RawRecordData:
    return _GROUPS


@pytest.fixture
def topic_rows() -> RawRecordData:
    return _TOPICS


@pytest.fixture
def user_rows() -> RawRecordData:
    return _USERS


@pytest.fixture
def department_rows() -> RawRecordData:
    return _DEPARTMENTS


@pytest.fixture
def user_department_rows() -> RawRecordData:
    return _USER_DEPARTMENTS


@pytest.fixture
def seed_insert_statements(
    group_rows: RawRecordData,
    topic_rows: RawRecordData,
    user_rows: RawRecordData,
    department_rows: RawRecordData,
    user_department_rows: RawRecordData,
) -> list[Insert]:
    return [
        insert(Group).values(group_rows),
        insert(Topic).values(topic_rows),
        insert(User).values(user_rows),
        insert(Department).values(department_rows),
        insert(UserDepartmentJoinTable).values(user_department_rows),
    ]


@pytest.mark.snapshot
async def test_isnull(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    query = """
        {
            users(filter: { bio: { isNull: true } }) {
                id
                bio
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["users"]) == len(_USERS) - 1
    assert result.data["users"] == [{"id": user["id"], "bio": user["bio"]} for user in _USERS if user["bio"] is None]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_to_many_filter_and_to_one_filter(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that a to-one filter next to a to-many filter restricts the parents through a join."""
    query = """
        {
            users(filter: { group: { name: { eq: "Group 1" } }, departments: { name: { eq: "IT" } } }) {
                name
            }
        }
    """
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data

    assert result.data["users"] == [{"name": "Alice"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field", "arguments"),
    [
        pytest.param("users", "", id="plain"),
        pytest.param("usersPaginated", "", id="paginated"),
        pytest.param("users", ", distinctOn: [name]", id="distinct-on"),
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ departments: { name: { isNull: true } } }", [], id="to-many-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { name: { isNull: true } } }', [], id="column-and-to-many-null"
        ),
        pytest.param("{ group: { name: { isNull: true } } }", [], id="to-one-null"),
        pytest.param('{ name: { neq: "Zed" }, group: { name: { isNull: true } } }', [], id="column-and-to-one-null"),
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
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { isNull: true } } }] }', ["Bob"], id="or-to-one-null"
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { departments: { name: { isNull: true } } }] }',
            ["Bob"],
            id="or-to-many-null",
        ),
        pytest.param(
            '{ _or: [{ name: { eq: "Bob" } }, { group: { name: { eq: "Group 1" } } }] }',
            ["Alice", "Bob"],
            id="or-to-one",
        ),
        pytest.param(
            "{ _not: { group: { name: { isNull: true } } } }",
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-to-one-null",
        ),
        pytest.param(
            '{ name: { neq: "Zed" }, _not: { group: { name: { isNull: true } } } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="column-and-not-to-one-null",
        ),
        pytest.param('{ _not: { group: { name: { eq: "Group 1" } } } }', ["Bob", "Charlie", "Tango"], id="not-to-one"),
        pytest.param(
            '{ name: { neq: "Zed" }, _not: { group: { name: { eq: "Group 1" } } } }',
            ["Bob", "Charlie", "Tango"],
            id="column-and-not-to-one",
        ),
        pytest.param("{ departments: { users: { group: { name: { isNull: true } } } } }", [], id="nested-to-one-null"),
        pytest.param(
            '{ name: { neq: "Zed" }, departments: { users: { group: { name: { isNull: true } } } } }',
            [],
            id="column-and-nested-to-one-null",
        ),
        pytest.param(
            '{ departments: { name: { neq: "Zed" }, users: { group: { name: { isNull: true } } } } }',
            [],
            id="nested-column-and-to-one-null",
        ),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } }, "
            "group: { name: { isNull: true } } }",
            [],
            id="aggregation-and-to-one-null",
        ),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } }, "
            "departments: { name: { isNull: true } } }",
            [],
            id="aggregation-and-to-many-null",
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
    ],
)
async def test_relation_filter_ignores_siblings(
    field: str, arguments: str, dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Test that a relation filter only matches rows having a matching related row, whatever its sibling filters."""
    result = await maybe_async(any_async_query(f"{{ {field}(filter: {dto_filter}{arguments}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data[field]) == names


@pytest.mark.snapshot
async def test_not_isnull(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query("{ users(filter: { _not: { bio: { isNull: true } } }) { name } }"))
    assert not result.errors
    assert result.data

    assert result.data["users"] == [{"name": "Tango"}]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ _not: { bio: { isNull: false } } }", ["Alice", "Bob", "Charlie"], id="not-isnull-false"),
        pytest.param('{ _not: { bio: { eq: "Tango\'s bio" } } }', ["Alice", "Bob", "Charlie"], id="not-eq"),
        pytest.param(
            '{ _not: { bio: { isNull: true, eq: "Tango\'s bio" } } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-isnull-and-eq",
        ),
        pytest.param(
            '{ _not: { _or: [{ bio: { isNull: true } }, { name: { eq: "Bob" } }] } }', ["Tango"], id="not-or-isnull"
        ),
        pytest.param("{ _not: { _not: { bio: { isNull: true } } } }", ["Alice", "Bob", "Charlie"], id="not-not-isnull"),
    ],
)
async def test_not_isnull_column(dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


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
            id="it-three-users-platform-two",
        )
    ],
)
async def test_aggregate_under_one_of_two_to_many_paths(
    any_async_query: AnyQueryExecutor,
    user_rows: RawRecordData,  # noqa: ARG001
    user_department_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """A user passes a count over its departments' users and a topic of its group when both hold for some rows."""
    dto_filter = (
        "{ departments: { usersAggregate: { count: { predicate: { gt: 1 } } } }, "
        'group: { topics: { name: { eq: "Hello!" } } } }'
    )

    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))

    assert not result.errors
    assert result.data is not None
    assert sorted(user["name"] for user in result.data["users"]) == ["Alice", "Dave"]


@pytest.mark.parametrize(
    ("group_rows", "user_rows", "department_rows"),
    [
        pytest.param(
            [
                {"id": 1, "name": "Group 1"},
                {"id": 2, "name": None},
                *({"id": i, "name": f"Group {i}"} for i in (3, 4, 5)),
            ],
            [
                {"id": 1, "name": "Alice", "group_id": 1, "bio": None},
                {"id": 2, "name": "Bob", "group_id": 2, "bio": None},
                {"id": 3, "name": "Charlie", "group_id": None, "bio": None},
                {"id": 4, "name": "Tango", "group_id": None, "bio": "Tango's bio"},
            ],
            [{"id": 1, "name": "IT"}, {"id": 2, "name": None}, {"id": 3, "name": "Platform"}],
            id="null-names",
        )
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ group: { name: { isNull: true } } }", ["Bob"], id="to-one-isnull"),
        pytest.param(
            "{ _not: { group: { name: { isNull: true } } } }", ["Alice", "Charlie", "Tango"], id="not-to-one-isnull"
        ),
        pytest.param(
            "{ _not: { group: { name: { isNull: false } } } }",
            ["Bob", "Charlie", "Tango"],
            id="not-to-one-isnull-false",
        ),
        pytest.param("{ group: { _not: { name: { isNull: true } } } }", ["Alice"], id="to-one-not-isnull"),
        pytest.param("{ departments: { name: { isNull: true } } }", ["Bob"], id="to-many-isnull"),
        pytest.param(
            "{ _not: { departments: { name: { isNull: true } } } }",
            ["Alice", "Charlie", "Tango"],
            id="not-to-many-isnull",
        ),
        pytest.param(
            "{ departments: { _not: { name: { isNull: true } } } }", ["Alice", "Charlie"], id="to-many-not-isnull"
        ),
    ],
)
async def test_not_isnull_relation(
    dto_filter: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    group_rows: RawRecordData,  # noqa: ARG001
    user_rows: RawRecordData,  # noqa: ARG001
    department_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test ``isNull`` on the columns of NULL-named related rows, directly and under ``_not``."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.snapshot
async def test_not_empty_comparison(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query("{ users(filter: { _not: { bio: {} } }) { name } }"))
    assert not result.errors
    assert result.data

    assert [user["name"] for user in result.data["users"]] == ["Alice", "Bob", "Charlie", "Tango"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("query", "variables", "names"),
    [
        pytest.param(
            "query ($bio: String) { users(filter: { _not: { bio: { eq: $bio } } }) { name } }",
            {},
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-omitted-variable",
        ),
        pytest.param(
            '{ users(filter: { _not: { bio: {}, name: { eq: "Bob" } } }) { name } }',
            None,
            ["Alice", "Charlie", "Tango"],
            id="not-empty-and-eq",
        ),
        pytest.param(
            "{ users(filter: { _not: { _and: [{ bio: {} }] } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-and-empty",
        ),
        pytest.param(
            "{ users(filter: { _not: { _or: [{ bio: {} }] } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-or-empty",
        ),
        pytest.param(
            '{ users(filter: { _not: { _or: [{ bio: {} }, { name: { eq: "Bob" } }] } }) { name } }',
            None,
            ["Alice", "Charlie", "Tango"],
            id="not-or-empty-and-eq",
        ),
        pytest.param(
            "{ users(filter: { _not: { _not: { bio: {} } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-not-empty",
        ),
        pytest.param(
            "{ users(filter: { group: { _not: { name: {} } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="to-one-not-empty",
        ),
        pytest.param(
            "{ users(filter: { departments: { _not: { name: {} } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="to-many-not-empty",
        ),
        pytest.param(
            "{ users(filter: { _not: { departmentsAggregate: { count: { arguments: [id], predicate: {} } } } }) "
            "{ name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-empty-aggregation",
        ),
    ],
)
async def test_empty_comparison_is_ignored(
    query: str, variables: dict[str, Any] | None, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    ("query", "variables"),
    [
        pytest.param("{ users(filter: { group: {} }) { name } }", None, id="to-one"),
        pytest.param("{ users(filter: { group: { name: {} } }) { name } }", None, id="to-one-empty-comparison"),
        pytest.param(
            "query ($name: String) { users(filter: { group: { name: { eq: $name } } }) { name } }",
            {},
            id="to-one-omitted-variable",
        ),
        pytest.param("{ users(filter: { _not: { group: {} } }) { name } }", None, id="not-to-one"),
        pytest.param(
            "{ users(filter: { _not: { group: { name: {} } } }) { name } }", None, id="not-to-one-empty-comparison"
        ),
        pytest.param("{ users(filter: { group: { topics: {} } }) { name } }", None, id="to-one-to-many"),
        pytest.param(
            "{ users(filter: { group: { topics: { name: {} } } }) { name } }",
            None,
            id="to-one-to-many-empty-comparison",
        ),
        pytest.param("{ users(filter: { group: { _and: [{ name: {} }] } }) { name } }", None, id="to-one-and"),
        pytest.param("{ users(filter: { group: { _or: [{ name: {} }] } }) { name } }", None, id="to-one-or"),
        pytest.param("{ users(filter: { departments: {} }) { name } }", None, id="to-many"),
        pytest.param("{ users(filter: { departments: { name: {} } }) { name } }", None, id="to-many-empty-comparison"),
        pytest.param("{ users(filter: { _not: { departments: {} } }) { name } }", None, id="not-to-many"),
        pytest.param(
            "{ users(filter: { _not: { departments: { name: {} } } }) { name } }",
            None,
            id="not-to-many-empty-comparison",
        ),
        pytest.param(
            "{ users(filter: { departments: { users: { name: {} } } }) { name } }", None, id="to-many-to-many"
        ),
        pytest.param(
            "{ users(filter: { _and: [{ departments: { name: {} } }, { group: {} }] }) { name } }",
            None,
            id="and-relations",
        ),
        pytest.param("{ users(filter: { departmentsAggregate: {} }) { name } }", None, id="aggregation"),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: {} } } }) { name } }",
            None,
            id="aggregation-empty-predicate",
        ),
        pytest.param("{ users(filter: { _not: { departmentsAggregate: {} } }) { name } }", None, id="not-aggregation"),
        pytest.param(
            "{ users(filter: { departments: { usersAggregate: {} } }) { name } }", None, id="to-many-aggregation"
        ),
    ],
)
async def test_empty_relation_filter_is_ignored(
    query: str, variables: dict[str, Any] | None, any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == ["Alice", "Bob", "Charlie", "Tango"]


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ group: { name: {} }, name: { eq: "Bob" } }', ["Bob"], id="to-one-and-column"),
        pytest.param('{ departments: { name: {} }, name: { eq: "Bob" } }', ["Bob"], id="to-many-and-column"),
        pytest.param(
            '{ departments: { name: {} }, group: { name: { eq: "Group 1" } } }', ["Alice"], id="to-many-and-to-one"
        ),
        pytest.param('{ _not: { group: { name: {} }, name: { eq: "Bob" } } }', ["Alice", "Charlie", "Tango"], id="not"),
    ],
)
async def test_empty_relation_filter_beside_predicate(
    dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.snapshot
@pytest.mark.parametrize(
    "dto_filter",
    [
        pytest.param("{ group: { name: {} } }", id="to-one"),
        pytest.param("{ departments: { name: {} } }", id="to-many"),
        pytest.param("{ _not: { departments: { name: {} } } }", id="not-to-many"),
    ],
)
async def test_empty_relation_filter(
    dto_filter: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data

    assert sorted(user["name"] for user in result.data["users"]) == ["Alice", "Bob", "Charlie", "Tango"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ _or: [] }", ["Alice", "Bob", "Charlie", "Tango"], id="no-branch"),
        pytest.param("{ _or: [{}, {}] }", ["Alice", "Bob", "Charlie", "Tango"], id="empty-branches"),
        pytest.param("{ _or: [{ bio: {} }] }", ["Alice", "Bob", "Charlie", "Tango"], id="empty-comparison"),
        pytest.param('{ _or: [{}, { name: { eq: "Bob" } }] }', ["Bob"], id="empty-and-eq"),
        pytest.param('{ _or: [{ bio: {} }, { name: { eq: "Bob" } }] }', ["Bob"], id="empty-comparison-and-eq"),
        pytest.param('{ _or: [{ _not: { bio: {} } }, { name: { eq: "Bob" } }] }', ["Bob"], id="empty-not-and-eq"),
        pytest.param('{ _or: [{ _and: [{ bio: {} }] }, { name: { eq: "Bob" } }] }', ["Bob"], id="empty-and-and-eq"),
        pytest.param('{ _or: [{ group: {} }, { name: { eq: "Bob" } }] }', ["Bob"], id="to-one-and-eq"),
        pytest.param('{ _or: [{ group: { name: {} } }, { name: { eq: "Bob" } }] }', ["Bob"], id="to-one-empty-and-eq"),
        pytest.param('{ _or: [{ departments: {} }, { name: { eq: "Bob" } }] }', ["Bob"], id="to-many-and-eq"),
        pytest.param(
            '{ _or: [{ departments: { name: {} } }, { name: { eq: "Bob" } }] }', ["Bob"], id="to-many-empty-and-eq"
        ),
        pytest.param(
            '{ _or: [{ departmentsAggregate: {} }, { name: { eq: "Bob" } }] }', ["Bob"], id="aggregation-and-eq"
        ),
        pytest.param(
            '{ group: { _or: [{ name: {} }, { name: { eq: "Group 1" } }] } }', ["Alice"], id="to-one-or-empty-and-eq"
        ),
        pytest.param(
            '{ departments: { _or: [{ name: {} }, { name: { eq: "IT" } }] } }',
            ["Alice", "Charlie"],
            id="to-many-or-empty-and-eq",
        ),
        pytest.param(
            '{ _not: { _or: [{ group: { name: {} } }, { name: { eq: "Bob" } }] } }',
            ["Alice", "Charlie", "Tango"],
            id="not-or-to-one-empty-and-eq",
        ),
        pytest.param(
            '{ _not: { _or: [{ departments: { name: {} } }, { name: { eq: "Bob" } }] } }',
            ["Alice", "Charlie", "Tango"],
            id="not-or-to-many-empty-and-eq",
        ),
        pytest.param(
            '{ _or: [{ _or: [{ bio: {} }] }, { name: { eq: "Bob" } }] }', ["Bob"], id="nested-or-empty-and-eq"
        ),
    ],
)
async def test_empty_or_branch_is_pruned(dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor) -> None:
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param("{ name: null }", ["Alice", "Bob", "Charlie", "Tango"], id="column"),
        pytest.param("{ group: null }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one"),
        pytest.param("{ group: { name: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-column"),
        pytest.param("{ group: { topics: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-to-many"),
        pytest.param("{ departments: null }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many"),
        pytest.param("{ departments: { name: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many-column"),
        pytest.param("{ departmentsAggregate: null }", ["Alice", "Bob", "Charlie", "Tango"], id="aggregation"),
        pytest.param(
            "{ departmentsAggregate: { count: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="aggregation-function"
        ),
        pytest.param(
            "{ departments: { usersAggregate: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-many-aggregation"
        ),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: null, predicate: { gt: 0 } } } }",
            ["Alice", "Bob", "Charlie"],
            id="aggregation-arguments",
        ),
        pytest.param(
            "{ _not: { departmentsAggregate: { count: { arguments: null, predicate: { gt: 0 } } } } }",
            ["Tango"],
            id="not-aggregation-arguments",
        ),
        pytest.param("{ _not: null }", ["Alice", "Bob", "Charlie", "Tango"], id="not"),
        pytest.param("{ _not: { name: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-column"),
        pytest.param("{ _not: { group: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-to-one"),
        pytest.param("{ _not: { departments: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="not-to-many"),
        pytest.param(
            "{ _not: { departmentsAggregate: { count: null } } }",
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-aggregation-function",
        ),
        pytest.param("{ group: { _not: null } }", ["Alice", "Bob", "Charlie", "Tango"], id="to-one-not"),
        pytest.param("{ _and: [{ group: null }] }", ["Alice", "Bob", "Charlie", "Tango"], id="and"),
        pytest.param("{ _or: [{ departments: null }] }", ["Alice", "Bob", "Charlie", "Tango"], id="or"),
        pytest.param('{ group: null, name: { eq: "Bob" } }', ["Bob"], id="to-one-and-column"),
        pytest.param('{ departmentsAggregate: null, name: { eq: "Bob" } }', ["Bob"], id="aggregation-and-column"),
        pytest.param('{ _not: null, name: { eq: "Bob" } }', ["Bob"], id="not-and-column"),
        pytest.param('{ _or: [{ departments: null }, { name: { eq: "Bob" } }] }', ["Bob"], id="or-to-many-and-column"),
        pytest.param(
            '{ departments: null, _and: [{ departments: { name: { eq: "IT" } } }] }',
            ["Alice", "Charlie"],
            id="to-many-and-to-many-branch",
        ),
        pytest.param(
            '{ _not: { departments: { name: null }, name: { eq: "Bob" } } }',
            ["Alice", "Charlie", "Tango"],
            id="not-to-many-and-column",
        ),
    ],
)
async def test_null_filter_field_is_ignored(
    dto_filter: str, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Test that a filter field set to null filters nothing, as if it were absent."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {dto_filter}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("query ($value: GroupBoolExp) { users(filter: { group: $value }) { name } }", id="to-one"),
        pytest.param("query ($value: TextComparison) { users(filter: { name: $value }) { name } }", id="column"),
        pytest.param("query ($value: UserFilter) { users(filter: $value) { name } }", id="filter"),
    ],
)
async def test_null_filter_variable_is_ignored(query: str, any_async_query: AnyQueryExecutor) -> None:
    """Test that a filter bound to a null variable filters nothing."""
    result = await maybe_async(any_async_query(query, {"value": None}))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == ["Alice", "Bob", "Charlie", "Tango"]


@pytest.mark.parametrize(
    ("department_rows", "user_department_rows"),
    [
        pytest.param(
            [
                {"id": 1, "name": "IT"},
                {"id": 2, "name": "Sales"},
                {"id": 3, "name": "Platform"},
                {"id": 4, "name": None},
            ],
            [
                {"user_id": 1, "department_id": 1},
                {"user_id": 1, "department_id": 4},
                {"user_id": 2, "department_id": 2},
                {"user_id": 3, "department_id": 3},
                {"user_id": 3, "department_id": 1},
            ],
            id="null-department",
        )
    ],
)
@pytest.mark.parametrize(
    "topic_rows",
    [
        pytest.param(
            [
                {"id": 1, "name": "Hello!", "group_id": 1},
                {"id": 2, "name": "Problems", "group_id": 2},
                {"id": 3, "name": "Welcome", "group_id": 1},
            ],
            id="group-with-two-topics",
        )
    ],
)
@pytest.mark.parametrize(
    ("field", "arguments"),
    [
        pytest.param("users", "", id="plain"),
        pytest.param("usersPaginated", "", id="paginated"),
        pytest.param("users", ", distinctOn: [name]", id="distinct-on"),
    ],
)
@pytest.mark.parametrize(
    ("dto_filter", "names"),
    [
        pytest.param('{ departments: { name: { eq: "IT" } } }', ["Bob", "Tango"], id="to-many"),
        pytest.param('{ departments: { users: { name: { eq: "Alice" } } } }', ["Bob", "Tango"], id="nested-to-many"),
        pytest.param(
            '{ departments: { _not: { users: { name: { eq: "Alice" } } } } }',
            ["Alice", "Tango"],
            id="to-many-not-nested-to-many",
        ),
        pytest.param(
            '{ _and: [{ departments: { name: { eq: "IT" } } }, { name: { neq: "Alice" } }] }',
            ["Alice", "Bob", "Tango"],
            id="and-to-many",
        ),
        pytest.param(
            '{ _or: [{ departments: { name: { eq: "Sales" } } }, { name: { eq: "Alice" } }] }',
            ["Charlie", "Tango"],
            id="or-to-many-and-column",
        ),
        pytest.param(
            '{ name: { eq: "Charlie" }, departments: { name: { eq: "IT" } } }',
            ["Alice", "Bob", "Tango"],
            id="column-and-to-many",
        ),
        pytest.param(
            '{ group: { name: { eq: "Group 1" } }, departments: { name: { eq: "IT" } } }',
            ["Bob", "Charlie", "Tango"],
            id="to-one-and-to-many",
        ),
        pytest.param(
            '{ _or: [{ group: { name: { eq: "Group 1" } } }, { departments: { name: { eq: "Sales" } } }] }',
            ["Charlie", "Tango"],
            id="or-to-one-and-to-many",
        ),
        pytest.param('{ _not: { departments: { name: { eq: "IT" } } } }', ["Alice", "Charlie"], id="not-to-many"),
        pytest.param('{ departments: { _not: { name: { eq: "IT" } } } }', ["Tango"], id="to-many-not"),
        pytest.param(
            "{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }",
            ["Bob", "Tango"],
            id="aggregation",
        ),
        pytest.param('{ group: { name: { eq: "Group 1" } } }', ["Bob", "Charlie", "Tango"], id="to-one"),
        pytest.param(
            '{ group: { topics: { name: { eq: "Hello!" } } } }', ["Bob", "Charlie", "Tango"], id="to-one-to-many"
        ),
        pytest.param(
            '{ group: { _not: { topics: { name: { eq: "Problems" } } } } }',
            ["Bob", "Charlie", "Tango"],
            id="to-one-not-to-many",
        ),
        pytest.param(
            '{ _and: [{ departments: { name: { eq: "IT" } } }, { departments: { name: { eq: "Platform" } } }] }',
            ["Alice", "Bob", "Tango"],
            id="and-same-to-many",
        ),
        pytest.param(
            '{ departments: { name: { eq: "IT" } }, _and: [{ departments: { name: { eq: "Platform" } } }] }',
            ["Alice", "Bob", "Tango"],
            id="to-many-and-same-to-many",
        ),
        pytest.param(
            '{ _and: [{ _and: [{ departments: { name: { eq: "IT" } } }] }, '
            '{ departments: { name: { eq: "Platform" } } }] }',
            ["Alice", "Bob", "Tango"],
            id="nested-and-same-to-many",
        ),
        pytest.param(
            '{ departments: { name: { eq: "IT" } }, '
            '_or: [{ departments: { name: { eq: "Platform" } } }, { name: { eq: "Bob" } }] }',
            ["Alice", "Bob", "Tango"],
            id="to-many-and-or-same-to-many",
        ),
        pytest.param(
            '{ _and: [{ _or: [{ departments: { name: { eq: "Sales" } } }, '
            '{ departments: { name: { eq: "Platform" } } }] }, { departments: { name: { eq: "IT" } } }] }',
            ["Alice", "Bob", "Tango"],
            id="and-or-same-to-many",
        ),
        pytest.param(
            '{ _or: [{ departments: { name: { eq: "IT" } } }, { departments: { name: { eq: "Platform" } } }] }',
            ["Bob", "Tango"],
            id="or-same-to-many",
        ),
        pytest.param(
            '{ departments: { _and: [{ name: { eq: "IT" } }, { name: { eq: "Platform" } }] } }',
            ["Alice", "Bob", "Charlie", "Tango"],
            id="to-many-and-same-row",
        ),
        pytest.param(
            '{ _and: [{ _not: { departments: { name: { eq: "IT" } } } }, { departments: { name: { eq: "Sales" } } }] }',
            ["Alice", "Charlie", "Tango"],
            id="and-not-to-many",
        ),
        pytest.param(
            '{ _and: [{ departments: { name: { eq: "Platform" } } }, '
            '{ departments: { users: { name: { eq: "Alice" } } } }] }',
            ["Alice", "Bob", "Tango"],
            id="and-same-to-many-nested-to-many",
        ),
        pytest.param(
            '{ departments: { _and: [{ users: { name: { eq: "Alice" } } }, { users: { name: { eq: "Charlie" } } }] } }',
            ["Bob", "Tango"],
            id="to-many-and-same-nested-to-many",
        ),
        pytest.param(
            '{ group: { _and: [{ topics: { name: { eq: "Hello!" } } }, { topics: { name: { eq: "Welcome" } } }] } }',
            ["Bob", "Charlie", "Tango"],
            id="to-one-and-same-to-many",
        ),
        pytest.param(
            '{ _and: [{ group: { topics: { name: { eq: "Hello!" } } } }, '
            '{ group: { topics: { name: { eq: "Welcome" } } } }] }',
            ["Bob", "Charlie", "Tango"],
            id="and-to-one-same-to-many",
        ),
        pytest.param(
            "{ _and: [{ departmentsAggregate: { count: { arguments: [id], predicate: { gt: 1 } } } }, "
            '{ departments: { name: { eq: "IT" } } }, { departments: { name: { isNull: true } } }] }',
            ["Bob", "Charlie", "Tango"],
            id="and-aggregation-same-to-many",
        ),
    ],
)
async def test_not_complements_relation_filter(
    field: str,
    arguments: str,
    dto_filter: str,
    names: list[str],
    any_async_query: AnyQueryExecutor,
    department_rows: RawRecordData,  # noqa: ARG001
    user_department_rows: RawRecordData,  # noqa: ARG001
    topic_rows: RawRecordData,  # noqa: ARG001
) -> None:
    """Test that ``_not`` over a filter matches exactly the rows the filter does not."""
    query = "{{ {field}(filter: {dto_filter}{arguments}) {{ name }} }}"
    result = await maybe_async(any_async_query(query.format(field=field, dto_filter=dto_filter, arguments=arguments)))
    assert not result.errors
    assert result.data is not None
    matched = [user["name"] for user in result.data[field]]

    negated_filter = f"{{ _not: {dto_filter} }}"
    result = await maybe_async(
        any_async_query(query.format(field=field, dto_filter=negated_filter, arguments=arguments))
    )
    assert not result.errors
    assert result.data is not None
    negated = sorted(user["name"] for user in result.data[field])

    assert negated == names
    assert sorted(matched + negated) == ["Alice", "Bob", "Charlie", "Tango"]


@pytest.mark.snapshot
async def test_not_to_many(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query('{ users(filter: { _not: { departments: { name: { eq: "IT" } } } }) { name } }')
    )
    assert not result.errors
    assert result.data

    assert sorted(user["name"] for user in result.data["users"]) == ["Bob", "Tango"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_and_same_to_many(
    any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(
        any_async_query(
            "{ users(filter: { _and: ["
            '{ departments: { name: { eq: "IT" } } }, { departments: { name: { eq: "Platform" } } }'
            "] }) { name } }"
        )
    )
    assert not result.errors
    assert result.data

    assert [user["name"] for user in result.data["users"]] == ["Charlie"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
@pytest.mark.parametrize("comparison", ["in", "nin"])
async def test_empty_list_comparison(
    comparison: str, any_async_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_async_query(f"{{ users(filter: {{ bio: {{ {comparison}: [] }} }}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert [user["name"] for user in result.data["users"]] == (
        [] if comparison == "in" else ["Alice", "Bob", "Charlie", "Tango"]
    )
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("query", "variables", "names"),
    [
        pytest.param("{ users(filter: { name: { in: [] } }) { name } }", None, [], id="in"),
        pytest.param(
            "{ users(filter: { name: { nin: [] } }) { name } }", None, ["Alice", "Bob", "Charlie", "Tango"], id="nin"
        ),
        pytest.param(
            "{ users(filter: { _not: { bio: { in: [] } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-in",
        ),
        pytest.param("{ users(filter: { _not: { bio: { nin: [] } } }) { name } }", None, [], id="not-nin"),
        pytest.param("{ users(filter: { _not: { _not: { bio: { in: [] } } } }) { name } }", None, [], id="not-not-in"),
        pytest.param(
            '{ users(filter: { _not: { bio: { in: [], eq: "Tango\'s bio" } } }) { name } }',
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-in-and-eq",
        ),
        pytest.param(
            '{ users(filter: { _not: { bio: { nin: [], eq: "Tango\'s bio" } } }) { name } }',
            None,
            ["Alice", "Bob", "Charlie"],
            id="not-nin-and-eq",
        ),
        pytest.param(
            "{ users(filter: { _not: { bio: { nin: [], isNull: true } } }) { name } }",
            None,
            ["Tango"],
            id="not-nin-and-is-null",
        ),
        pytest.param(
            '{ users(filter: { _or: [{ bio: { in: [] } }, { name: { eq: "Bob" } }] }) { name } }',
            None,
            ["Bob"],
            id="or-in",
        ),
        pytest.param(
            "query ($names: [String!]) { users(filter: { name: { in: $names } }) { name } }",
            {"names": []},
            [],
            id="in-variable",
        ),
        pytest.param(
            "{ users(filter: { bio: { in: null } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="in-null",
        ),
        pytest.param(
            "{ users(filter: { _not: { bio: { nin: null } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-nin-null",
        ),
        pytest.param("{ users(filter: { group: { name: { in: [] } } }) { name } }", None, [], id="to-one-in"),
        pytest.param("{ users(filter: { group: { name: { nin: [] } } }) { name } }", None, ["Alice"], id="to-one-nin"),
        pytest.param(
            "{ users(filter: { departments: { name: { nin: [] } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie"],
            id="to-many-nin",
        ),
        pytest.param(
            "{ users(filter: { _not: { departments: { name: { in: [] } } } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-to-many-in",
        ),
        pytest.param(
            "{ users(filter: { _not: { departments: { name: { nin: [] } } } }) { name } }",
            None,
            ["Tango"],
            id="not-to-many-nin",
        ),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: { in: [] } } } }) "
            "{ name } }",
            None,
            [],
            id="aggregation-in",
        ),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: { nin: [] } } } }) "
            "{ name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="aggregation-nin",
        ),
        pytest.param(
            "{ users(filter: { _not: { departmentsAggregate: { count: { arguments: [id], predicate: { in: [] } } } } "
            "}) { name } }",
            None,
            ["Alice", "Bob", "Charlie", "Tango"],
            id="not-aggregation-in",
        ),
    ],
)
async def test_empty_list_comparison_result(
    query: str, variables: dict[str, Any] | None, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names


@pytest.mark.parametrize("operator", _TEXT_OPERATORS)
@pytest.mark.parametrize(
    "template",
    [
        pytest.param("{{ bio: {{ {operator}: null }} }}", id="column"),
        pytest.param("{{ _not: {{ bio: {{ {operator}: null }} }} }}", id="not-column"),
    ],
)
async def test_null_operator_is_ignored(template: str, operator: str, any_async_query: AnyQueryExecutor) -> None:
    """Test that an operator set to null is ignored like an absent one, directly and under ``_not``."""
    result = await maybe_async(any_async_query(f"{{ users(filter: {template.format(operator=operator)}) {{ name }} }}"))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == _ALL_USERS


@pytest.mark.parametrize(
    ("query", "variables", "names"),
    [
        pytest.param(
            "query ($bio: String) { users(filter: { bio: { eq: $bio } }) { name } }",
            {"bio": None},
            _ALL_USERS,
            id="null-variable",
        ),
        pytest.param(
            "query ($bio: String) { users(filter: { _not: { bio: { neq: $bio } } }) { name } }",
            {"bio": None},
            _ALL_USERS,
            id="not-null-variable",
        ),
        pytest.param(
            "{ users(filter: { bio: { eq: null, isNull: true } }) { name } }",
            None,
            ["Alice", "Bob", "Charlie"],
            id="null-beside-operator",
        ),
        pytest.param(
            '{ users(filter: { _not: { name: { eq: "Bob", neq: null, isNull: null } } }) { name } }',
            None,
            ["Alice", "Charlie", "Tango"],
            id="not-null-beside-operator",
        ),
        pytest.param('{ users(filter: { bio: { eq: null }, name: { eq: "Bob" } }) { name } }', None, ["Bob"], id="and"),
        pytest.param(
            '{ users(filter: { _or: [{ bio: { eq: null } }, { name: { eq: "Bob" } }] }) { name } }',
            None,
            ["Bob"],
            id="or-branch",
        ),
        pytest.param("{ users(filter: { group: { name: { eq: null } } }) { name } }", None, _ALL_USERS, id="to-one"),
        pytest.param(
            "{ users(filter: { group: { name: { isNull: null } } }) { name } }", None, _ALL_USERS, id="to-one-isnull"
        ),
        pytest.param(
            "{ users(filter: { _not: { group: { name: { eq: null } } } }) { name } }",
            None,
            _ALL_USERS,
            id="not-to-one",
        ),
        pytest.param(
            "{ users(filter: { departments: { name: { gt: null } } }) { name } }", None, _ALL_USERS, id="to-many"
        ),
        pytest.param(
            "{ users(filter: { _not: { departments: { name: { like: null } } } }) { name } }",
            None,
            _ALL_USERS,
            id="not-to-many",
        ),
        pytest.param(
            "{ users(filter: { departments: { _not: { name: { neq: null } } } }) { name } }",
            None,
            _ALL_USERS,
            id="to-many-not",
        ),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: { eq: null } } } }) "
            "{ name } }",
            None,
            _ALL_USERS,
            id="aggregation-eq",
        ),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: { gt: null, "
            "isNull: null, in: null } } } }) { name } }",
            None,
            _ALL_USERS,
            id="aggregation-operators",
        ),
        pytest.param(
            "{ users(filter: { _not: { departmentsAggregate: { count: { arguments: [id], "
            "predicate: { lte: null } } } } }) { name } }",
            None,
            _ALL_USERS,
            id="not-aggregation",
        ),
        pytest.param(
            "{ users(filter: { departmentsAggregate: { count: { arguments: [id], predicate: { eq: 1, neq: null } } } }) "
            "{ name } }",
            None,
            ["Alice", "Bob"],
            id="aggregation-null-beside-operator",
        ),
    ],
)
async def test_null_operator_is_ignored_in_filter(
    query: str, variables: dict[str, Any] | None, names: list[str], any_async_query: AnyQueryExecutor
) -> None:
    """Test that null operators are ignored beside other operators, in branches, relations and aggregations."""
    result = await maybe_async(any_async_query(query, variables))
    assert not result.errors
    assert result.data is not None

    assert sorted(user["name"] for user in result.data["users"]) == names
