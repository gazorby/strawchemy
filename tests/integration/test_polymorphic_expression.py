from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Insert, MetaData, insert

from tests.integration.models import ExprGarage, ExprVehicle, expression_polymorphic_metadata
from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.integration.typing import RawRecordData
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker

pytestmark = [pytest.mark.integration]


@pytest.fixture
def raw_garages() -> RawRecordData:
    return [{"id": 1, "name": "North"}, {"id": 2, "name": "South"}]


@pytest.fixture
def raw_vehicles() -> RawRecordData:
    return [
        {"id": 1, "name": "Car", "wheels": 4, "garage_id": 1},
        {"id": 2, "name": "BMX", "wheels": 2, "garage_id": 1},
        {"id": 3, "name": "Truck", "wheels": 6, "garage_id": 2},
        {"id": 4, "name": "Racer", "wheels": 2, "garage_id": 2},
    ]


@pytest.fixture
def metadata() -> MetaData:
    return expression_polymorphic_metadata


@pytest.fixture
def seed_insert_statements(raw_garages: RawRecordData, raw_vehicles: RawRecordData) -> list[Insert]:
    return [insert(ExprGarage).values(raw_garages), insert(ExprVehicle).values(raw_vehicles)]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.ExprVehicleAsyncQuery
    if dialect == "mysql":
        return mysql_types.ExprVehicleAsyncQuery
    return sqlite_types.ExprVehicleAsyncQuery


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.ExprVehicleSyncQuery
    if dialect == "mysql":
        return mysql_types.ExprVehicleSyncQuery
    return sqlite_types.ExprVehicleSyncQuery


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "{ vehicles { id name wheels } }",
            {
                "vehicles": [
                    {"id": 1, "name": "Car", "wheels": 4},
                    {"id": 2, "name": "BMX", "wheels": 2},
                    {"id": 3, "name": "Truck", "wheels": 6},
                    {"id": 4, "name": "Racer", "wheels": 2},
                ]
            },
            id="base",
        ),
        pytest.param(
            "{ bikes { id name } }",
            {"bikes": [{"id": 2, "name": "BMX"}, {"id": 4, "name": "Racer"}]},
            id="subclass",
        ),
        pytest.param(
            "{ vehicles(filter: { wheels: { gt: 2 } }, orderBy: [{ wheels: DESC }]) { id } }",
            {"vehicles": [{"id": 3}, {"id": 1}]},
            id="base-filter-order-by",
        ),
        pytest.param(
            '{ bikes(filter: { name: { neq: "BMX" } }) { id } }',
            {"bikes": [{"id": 4}]},
            id="subclass-filter",
        ),
        pytest.param(
            "{ bikes(orderBy: [{ name: DESC }]) { name } }",
            {"bikes": [{"name": "Racer"}, {"name": "BMX"}]},
            id="subclass-order-by",
        ),
        pytest.param(
            "{ vehiclesPaginated(limit: 2, offset: 1, orderBy: [{ id: ASC }]) { id } }",
            {"vehiclesPaginated": [{"id": 2}, {"id": 3}]},
            id="base-paginated",
        ),
        pytest.param(
            "{ bikesPaginated(limit: 1, orderBy: [{ id: DESC }]) { id garage { name } } }",
            {"bikesPaginated": [{"id": 4, "garage": {"name": "South"}}]},
            id="subclass-paginated",
        ),
        pytest.param(
            "{ garages { name vehicles { id } bikes { id } } }",
            {
                "garages": [
                    {"name": "North", "vehicles": [{"id": 1}, {"id": 2}], "bikes": [{"id": 2}]},
                    {"name": "South", "vehicles": [{"id": 3}, {"id": 4}], "bikes": [{"id": 4}]},
                ]
            },
            id="relations",
        ),
    ],
)
async def test_expression_discriminator(
    query: str, expected: dict[str, Any], any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that types of a model with an expression `polymorphic_on` query the right rows in one statement."""
    result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data == expected
    assert query_tracker.query_count == 1
