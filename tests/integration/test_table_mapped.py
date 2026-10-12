from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import strawberry
from sqlalchemy import Insert, MetaData, insert

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import TableMappedColor, TableMappedFruit, table_mapped_metadata
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(TableMappedFruit, include=["id", "name", "color_id", "color"])
    class TableMappedFruitType: ...

    @strawberry.type
    class Query:
        table_mapped_fruits: list[TableMappedFruitType] = strawchemy.field()

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


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


async def test_null_column_and_to_one_relation(any_query: AnyQueryExecutor) -> None:
    """Test that NULL values of a model mapped without `Mapped` hints are returned as null."""
    result = await maybe_async(any_query("{ tableMappedFruits { id name colorId color { name } } }"))

    assert not result.errors
    assert result.data
    assert sorted(result.data["tableMappedFruits"], key=lambda fruit: fruit["id"]) == [
        {"id": 1, "name": "Apple", "colorId": 1, "color": {"name": "Red"}},
        {"id": 2, "name": None, "colorId": None, "color": None},
    ]
