from __future__ import annotations

from typing import Any, override

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from strawberry import Info
from strawberry.extensions.field_extension import AsyncExtensionResolver, FieldExtension, SyncExtensionResolver
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .types import FruitFilter, FruitTypeHooks, strawchemy
from .typing import RawRecordData


class SomeExtension(FieldExtension):
    @override
    async def resolve_async(self, next_: AsyncExtensionResolver, source: Any, info: Info, **kwargs: Any) -> Any:
        fruit = await next_(source, info, **kwargs)
        assert fruit.instance.name == "Apple"
        return fruit

    @override
    def resolve(self, next_: SyncExtensionResolver, source: Any, info: Info, **kwargs: Any) -> Any:
        fruit = next_(source, info, **kwargs)
        assert fruit.instance.name == "Apple"
        return fruit


@strawberry.type
class AsyncQuery:
    fruit_by_id: FruitTypeHooks = strawchemy.field(
        filter_input=FruitFilter, repository_type=StrawchemyAsyncRepository, extensions=[SomeExtension()]
    )


@strawberry.type
class SyncQuery:
    fruit_by_id: FruitTypeHooks = strawchemy.field(
        filter_input=FruitFilter, repository_type=StrawchemySyncRepository, extensions=[SomeExtension()]
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


async def test_field_extension(any_query: AnyQueryExecutor, raw_fruits: RawRecordData) -> None:
    result = await maybe_async(
        any_query(
            """
            query fruitById($id: UUID!) {
                fruitById(id: $id) {
                    name
            }
            }
            """,
            {"id": raw_fruits[0]["id"]},
        )
    )

    assert not result.errors
    assert result.data
    assert result.data["fruitById"] == {"name": raw_fruits[0]["name"]}
