from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, MetaData, insert

from tests.integration.fixtures import Operations, SchemaTypes
from tests.integration.models import ExprBike, ExprGarage, ExprVehicle, expression_polymorphic_metadata
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker

pytestmark = [pytest.mark.integration]

_GARAGES: list[dict[str, Any]] = [{"id": 1, "name": "North"}, {"id": 2, "name": "South"}]
_VEHICLES: list[dict[str, Any]] = [
    {"id": 1, "name": "Car", "wheels": 4, "garage_id": 1},
    {"id": 2, "name": "BMX", "wheels": 2, "garage_id": 1},
    {"id": 3, "name": "Truck", "wheels": 6, "garage_id": 2},
    {"id": 4, "name": "Racer", "wheels": 2, "garage_id": 2},
]


@pytest.fixture
def metadata() -> MetaData:
    return expression_polymorphic_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(ExprGarage).values(_GARAGES), insert(ExprVehicle).values(_VEHICLES)]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.filter(ExprVehicle, include=["name", "wheels"])
    class ExprVehicleFilter: ...

    @strawchemy.order(ExprVehicle, include=["id", "wheels"])
    class ExprVehicleOrderBy: ...

    @strawchemy.type(ExprVehicle, include=["id", "name", "wheels"])
    class ExprVehicleType: ...

    @strawchemy.filter(ExprBike, include=["name"])
    class ExprBikeFilter: ...

    @strawchemy.order(ExprBike, include=["id", "name"])
    class ExprBikeOrderBy: ...

    @strawchemy.type(ExprBike, include=["id", "name", "garage"], scope="schema")
    class ExprBikeType: ...

    @strawchemy.type(ExprGarage, include=["name", "vehicles", "bikes"], scope="schema")
    class ExprGarageType: ...

    @strawberry.type
    class Query:
        vehicles: list[ExprVehicleType] = strawchemy.field(
            filter_input=ExprVehicleFilter, order_by_input=ExprVehicleOrderBy
        )
        vehicles_paginated: list[ExprVehicleType] = strawchemy.field(
            filter_input=ExprVehicleFilter, order_by_input=ExprVehicleOrderBy, pagination=True
        )
        bikes: list[ExprBikeType] = strawchemy.field(filter_input=ExprBikeFilter, order_by_input=ExprBikeOrderBy)
        bikes_paginated: list[ExprBikeType] = strawchemy.field(
            filter_input=ExprBikeFilter, order_by_input=ExprBikeOrderBy, pagination=True
        )
        garages: list[ExprGarageType] = strawchemy.field()

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


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
