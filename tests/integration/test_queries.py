from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from graphql import GraphQLError

from strawberry.types import get_object_definition
from tests.typing import AnyQueryExecutor, SyncQueryExecutor
from tests.utils import maybe_async

from .types.postgres import UserType
from .typing import RawRecordData

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from .fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


def test_required_id_single(no_session_query: SyncQueryExecutor) -> None:
    result = no_session_query("{ user { name } }")

    assert bool(result.errors)
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], GraphQLError)
    assert result.errors[0].message == "Field 'user' argument 'id' of type 'Int!' is required, but it was not provided."


async def test_single(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query GetUser($id: Int!) {
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


async def test_typename_do_not_fail(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    __typename
            }
            }
            """,
            {"id": raw_users[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"__typename": get_object_definition(UserType, strict=True).name}


async def test_many(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(any_query("{ users { name } }"))

    assert not result.errors
    assert result.data
    assert result.data["users"] == [{"name": user["name"]} for user in raw_users]


async def test_relation(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query("{ fruits { color { id } } }"))

    assert not result.errors
    assert result.data
    assert result.data["fruits"] == [{"color": {"id": fruit["color_id"]}} for fruit in raw_fruits]


async def test_list_relation(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(any_query("{ colors { id fruits { name id } } }"))

    assert not result.errors
    assert result.data

    for color in result.data["colors"]:
        assert len(color["fruits"]) == len([f for f in raw_fruits if f["color_id"] == color["id"]])
        for fruit in color["fruits"]:
            expected = next(f for f in raw_fruits if f["id"] == fruit["id"])
            assert fruit == {"name": expected["name"], "id": expected["id"]}


async def test_column_property(any_query: AnyQueryExecutor, raw_users: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query GetUser($id: Int!) {
                user(id: $id) {
                    greeting
            }
            }
            """,
            {"id": raw_users[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["user"] == {"greeting": f"Hello, {raw_users[0]['name']}"}


@pytest.mark.snapshot
async def test_only_queried_columns_included_in_select(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    await maybe_async(any_query("{ colors { name fruits { name id } } }"))
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_filtered_statement(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    result = await maybe_async(any_query("{ colorsFiltered { name } }"))

    assert not result.errors
    assert result.data
    assert len(result.data["colorsFiltered"]) == 1
    assert result.data["colorsFiltered"][0]["name"] == "Red"

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
