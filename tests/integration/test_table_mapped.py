from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Insert, MetaData, insert

from tests.integration.models import TableMappedColor, TableMappedFruit, table_mapped_metadata
from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_TYPES_MODULES = {"postgresql": postgres_types, "mysql": mysql_types, "sqlite": sqlite_types}


@pytest.fixture
def metadata() -> MetaData:
    return table_mapped_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(TableMappedColor).values([{"id": 1, "name": "Red"}]),
        insert(TableMappedFruit).values(
            [{"id": 1, "name": "Apple", "color_id": 1}, {"id": 2, "name": None, "color_id": None}]
        ),
    ]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    return _TYPES_MODULES[dialect].TableMappedAsyncQuery


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    return _TYPES_MODULES[dialect].TableMappedSyncQuery


async def test_null_column_and_to_one_relation(any_query: AnyQueryExecutor) -> None:
    """Test that NULL values of a model mapped without `Mapped` hints are returned as null."""
    result = await maybe_async(any_query("{ tableMappedFruits { id name colorId color { name } } }"))

    assert not result.errors
    assert result.data
    assert sorted(result.data["tableMappedFruits"], key=lambda fruit: fruit["id"]) == [
        {"id": 1, "name": "Apple", "colorId": 1, "color": {"name": "Red"}},
        {"id": 2, "name": None, "colorId": None, "color": None},
    ]
