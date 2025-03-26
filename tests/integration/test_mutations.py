from __future__ import annotations

from uuid import uuid4

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from syrupy.assertion import SnapshotAssertion
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import ColorCreateInput, ColorType, strawchemy

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncMutation:
    create_color: ColorType = strawchemy.create_mutation(ColorCreateInput, repository_type=StrawchemyAsyncRepository)
    create_colors: list[ColorType] = strawchemy.create_mutation(
        ColorCreateInput, repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncMutation:
    create_color: ColorType = strawchemy.create_mutation(ColorCreateInput, repository_type=StrawchemySyncRepository)
    create_colors: list[ColorType] = strawchemy.create_mutation(
        ColorCreateInput, repository_type=StrawchemySyncRepository
    )


@strawberry.type
class SyncQuery:
    @strawberry.field
    def hello(self) -> str:
        return "world"


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def sync_mutation() -> type[SyncMutation]:
    return SyncMutation


@pytest.fixture
def async_mutation() -> type[AsyncMutation]:
    return AsyncMutation


@pytest.mark.snapshot
async def test_create_mutation(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    color_id = uuid4()
    result = await maybe_async(
        any_query(f'mutation {{ createColor(data: {{ id: "{color_id}", name: "new color" }}) {{ id name }} }}')
    )
    assert not result.errors
    assert result.data
    assert result.data["createColor"] == {"id": str(color_id), "name": "new color"}

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_create_many_mutation(
    any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    color_id_1, color_id_2 = uuid4(), uuid4()
    result = await maybe_async(
        any_query(
            f"""
                mutation {{
                    createColors(
                        data: [
                            {{ id: "{color_id_1}", name: "new color 1" }}
                            {{ id: "{color_id_2}", name: "new color 2" }}
                        ]
                    ) {{
                        id
                        name
                    }}
                }}
            """
        )
    )
    assert not result.errors
    assert result.data
    assert result.data["createColors"] == [
        {"id": str(color_id_1), "name": "new color 1"},
        {"id": str(color_id_2), "name": "new color 2"},
    ]

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
