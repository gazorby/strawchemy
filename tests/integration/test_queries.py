from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from graphql import GraphQLError
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import maybe_async

from .types import (
    ColorType,
    FruitFilter,
    FruitOrderBy,
    FruitTypeWithPaginationAndOrderBy,
    UserFilter,
    UserOrderBy,
    UserType,
    strawchemy,
)
from .typing import RawRecordData

if TYPE_CHECKING:
    from .fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemyAsyncRepository
    )
    user: UserType = strawchemy.field(repository_type=StrawchemyAsyncRepository)
    users: list[UserType] = strawchemy.field(
        filter_input=UserFilter,
        order_by=UserOrderBy,
        pagination=True,
        repository_type=StrawchemyAsyncRepository,
    )
    colors: list[ColorType] = strawchemy.field(repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    fruits: list[FruitTypeWithPaginationAndOrderBy] = strawchemy.field(
        filter_input=FruitFilter, order_by=FruitOrderBy, repository_type=StrawchemySyncRepository
    )
    user: UserType = strawchemy.field(repository_type=StrawchemySyncRepository)
    users: list[UserType] = strawchemy.field(
        filter_input=UserFilter, order_by=UserOrderBy, pagination=True, repository_type=StrawchemySyncRepository
    )
    colors: list[ColorType] = strawchemy.field(repository_type=StrawchemySyncRepository)


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


def test_required_id_single(no_session_query: SyncQueryExecutor) -> None:
    result = no_session_query("{ user { name } }")

    assert bool(result.errors)
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], GraphQLError)
    assert (
        result.errors[0].message == "Field 'user' argument 'id' of type 'UUID!' is required, but it was not provided."
    )


async def test_single(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query GetUser($id: UUID!) {
                user(id: $id) {
                    name
            }
            }
            """,
            {"id": raw_users[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"name": raw_users[0]["name"]}


async def test_many(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(any_query("{ users { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["users"] == [
        {"name": raw_users[0]["name"]},
        {"name": raw_users[1]["name"]},
        {"name": raw_users[2]["name"]},
    ]


async def test_relation(any_query: AnyQueryExecutor, raw_colors: RawRecordData) -> None:
    result = await maybe_async(any_query("{ fruits { color { id } } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruits"] == [
        {"color": {"id": raw_colors[0]["id"]}},
        {"color": {"id": raw_colors[1]["id"]}},
        {"color": {"id": raw_colors[2]["id"]}},
        {"color": {"id": raw_colors[3]["id"]}},
        {"color": {"id": raw_colors[4]["id"]}},
    ]


async def test_list_relation(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query("{ colors { fruits { name id } } }"))

    assert not result.errors

    expected = [
        {
            "fruits": [{"name": "Apple", "id": raw_fruits[0]["id"]}],
        },
        {
            "fruits": [{"name": "Banana", "id": raw_fruits[1]["id"]}],
        },
        {
            "fruits": [{"name": "Orange", "id": raw_fruits[2]["id"]}],
        },
        {
            "fruits": [{"name": "Strawberry", "id": raw_fruits[3]["id"]}],
        },
        {
            "fruits": [{"name": "Watermelon", "id": raw_fruits[4]["id"]}],
        },
    ]

    assert result.data
    assert all(fruit in result.data["colors"] for fruit in expected)


async def test_only_queried_columns_included_in_select(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    await maybe_async(any_query("{ colors { name fruits { name id } } }"))
    assert len(query_tracker.executions) == 1
    assert (
        str(query_tracker.executions[0].state.statement)
        == "SELECT DISTINCT color__fruits.name, color__fruits.id, color.name AS name_1, color.id AS id_1 \nFROM color AS color LEFT OUTER JOIN fruit AS color__fruits ON color.id = color__fruits.color_id"
    )
