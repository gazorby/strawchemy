from __future__ import annotations

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry

from .types import SQLDataTypesContainerType, strawchemy

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    sql_data_types_container: SQLDataTypesContainerType = strawchemy.field(repository_type=StrawchemyAsyncRepository)


@strawberry.type
class SyncQuery:
    sql_data_types_container: SQLDataTypesContainerType = strawchemy.field(repository_type=StrawchemySyncRepository)


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery
