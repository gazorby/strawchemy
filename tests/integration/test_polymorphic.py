from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Insert, MetaData, event, insert, inspect

from tests.integration.models import Bike, Car, Garage, Vehicle, polymorphic_metadata
from tests.integration.types import mysql as mysql_types
from tests.integration.types import postgres as postgres_types
from tests.integration.types import sqlite as sqlite_types
from tests.utils import maybe_async

if TYPE_CHECKING:
    from collections.abc import Generator

    from syrupy.assertion import SnapshotAssertion

    from strawchemy.typing import SupportedDialect
    from tests.integration.fixtures import QueryTracker
    from tests.typing import AnyQueryExecutor

pytestmark = [pytest.mark.integration]

# No page of the base class holds a car: loading one through the base class lazy-loads the car's own key.
_VEHICLES: list[dict[str, Any]] = [
    {"id": 1, "kind": "vehicle", "name": "Cart", "gears": None, "garage_id": 1},
    {"id": 2, "kind": "bike", "name": "Racer", "gears": 21, "garage_id": 1},
    {"id": 3, "kind": "vehicle", "name": "Wagon", "gears": None, "garage_id": 1},
    {"id": 4, "kind": "car", "name": "Sedan", "gears": None, "garage_id": 1},
    {"id": 5, "kind": "bike", "name": "Fixie", "gears": 1, "garage_id": 1},
    {"id": 6, "kind": "car", "name": "Van", "gears": None, "garage_id": 2},
    {"id": 7, "kind": "bike", "name": "Tandem", "gears": 7, "garage_id": 2},
    {"id": 8, "kind": "vehicle", "name": "Trailer", "gears": None, "garage_id": 2},
    {"id": 9, "kind": "bike", "name": "Cruiser", "gears": 3, "garage_id": 2},
    {"id": 10, "kind": "vehicle", "name": "Barrow", "gears": None, "garage_id": 4},
    {"id": 11, "kind": "vehicle", "name": "Sled", "gears": None, "garage_id": 4},
]
_CARS: list[dict[str, Any]] = [{"id": 4, "doors": 4}, {"id": 6, "doors": 5}]
_CLASSES: dict[str, type[Vehicle]] = {"vehicle": Vehicle, "car": Car, "bike": Bike}


@pytest.fixture
def metadata() -> MetaData:
    return polymorphic_metadata


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [
        insert(Garage).values([{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]),
        insert(polymorphic_metadata.tables["vehicle"]).values(_VEHICLES),
        insert(polymorphic_metadata.tables["car"]).values(_CARS),
    ]


@pytest.fixture
def async_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.PolymorphicAsyncQuery
    if dialect == "mysql":
        return mysql_types.PolymorphicAsyncQuery
    return sqlite_types.PolymorphicAsyncQuery


@pytest.fixture
def sync_query(dialect: SupportedDialect) -> type[Any]:
    if dialect == "postgresql":
        return postgres_types.PolymorphicSyncQuery
    if dialect == "mysql":
        return mysql_types.PolymorphicSyncQuery
    return sqlite_types.PolymorphicSyncQuery


@pytest.fixture
def loaded_vehicles() -> Generator[list[Vehicle]]:
    loaded: list[Vehicle] = []

    def collect(target: Vehicle, _: object) -> None:
        loaded.append(target)

    event.listen(Vehicle, "load", collect, propagate=True)
    yield loaded
    event.remove(Vehicle, "load", collect)


def _vehicles(*ids: int, keys: tuple[str, ...] = ("id", "name")) -> list[dict[str, Any]]:
    doors = {car["id"]: car["doors"] for car in _CARS}
    rows = [{**vehicle, "doors": doors.get(vehicle["id"])} for vehicle in _VEHICLES if vehicle["id"] in ids]
    return [{key: row[key] for key in keys} for row in rows]


def _assert_classes(loaded: list[Vehicle]) -> None:
    kinds = {vehicle["id"]: vehicle["kind"] for vehicle in _VEHICLES}
    assert loaded
    for instance in loaded:
        identity = inspect(instance).identity
        assert identity is not None
        (key,) = identity
        assert type(instance) is _CLASSES[kinds[key]]


async def _data(any_async_query: AnyQueryExecutor, query: str) -> dict[str, Any]:
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    return result.data


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("{ vehicles(limit: 2, offset: 1) { id name } }", {"vehicles": _vehicles(2, 3)}, id="base"),
        pytest.param(
            "{ cars(limit: 1, offset: 1) { id name doors } }",
            {"cars": _vehicles(6, keys=("id", "name", "doors"))},
            id="joined-table-subclass",
        ),
        pytest.param(
            "{ bikes(limit: 2, offset: 1) { id gears } }",
            {"bikes": _vehicles(5, 7, keys=("id", "gears"))},
            id="single-table-subclass",
        ),
    ],
)
@pytest.mark.snapshot
async def test_paginated_root(
    query: str,
    expected: dict[str, Any],
    any_async_query: AnyQueryExecutor,
    loaded_vehicles: list[Vehicle],
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a paginated root of a polymorphic model loads each row as the class of its discriminator."""
    assert await _data(any_async_query, query) == expected
    _assert_classes(loaded_vehicles)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        pytest.param(
            "vehicles(limit: 2, offset: 1) { id name }",
            [
                {"vehicles": _vehicles(2, 3)},
                {"vehicles": _vehicles(7, 8)},
                {"vehicles": []},
                {"vehicles": _vehicles(11)},
            ],
            id="base",
        ),
        pytest.param(
            "cars(limit: 1) { id doors }",
            [
                {"cars": _vehicles(4, keys=("id", "doors"))},
                {"cars": _vehicles(6, keys=("id", "doors"))},
                {"cars": []},
                {"cars": []},
            ],
            id="joined-table-subclass",
        ),
        pytest.param(
            "bikes(limit: 1, offset: 1) { id gears }",
            [
                {"bikes": _vehicles(5, keys=("id", "gears"))},
                {"bikes": _vehicles(9, keys=("id", "gears"))},
                {"bikes": []},
                {"bikes": []},
            ],
            id="single-table-subclass",
        ),
    ],
)
@pytest.mark.snapshot
async def test_paginated_relation(
    selection: str,
    expected: list[dict[str, Any]],
    any_async_query: AnyQueryExecutor,
    loaded_vehicles: list[Vehicle],
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that a paginated relation to a polymorphic model loads each row as the class of its discriminator."""
    assert await _data(any_async_query, f"{{ garages {{ {selection} }} }}") == {"garages": expected}
    _assert_classes(loaded_vehicles)
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        pytest.param(
            "bikes(orderBy: [{ id: DESC }]) { id }",
            [{"bikes": [{"id": 5}, {"id": 2}]}, {"bikes": [{"id": 9}, {"id": 7}]}, {"bikes": []}, {"bikes": []}],
            id="ordered",
        ),
        pytest.param(
            "first: bikes(limit: 1) { id } bikes { id }",
            [
                {"first": [{"id": 2}], "bikes": [{"id": 2}, {"id": 5}]},
                {"first": [{"id": 7}], "bikes": [{"id": 7}, {"id": 9}]},
                {"first": [], "bikes": []},
                {"first": [], "bikes": []},
            ],
            id="shared",
        ),
    ],
)
async def test_single_table_subclass_relation_keeps_parents_without_rows(
    selection: str, expected: list[dict[str, Any]], any_async_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that a parent without rows of a single-table subclass relation is kept, with an empty list."""
    assert await _data(any_async_query, f"{{ garages {{ {selection} }} }}") == {"garages": expected}
    assert query_tracker.query_count == 1


@pytest.mark.allow_duplicate_reads(
    reason="vehicles, cars and bikes are three relations to the vehicle table, and vehicles holds the rows of the others"
)
async def test_polymorphic_relations_of_paginated_root(
    any_async_query: AnyQueryExecutor, loaded_vehicles: list[Vehicle], query_tracker: QueryTracker
) -> None:
    """Test that relations to polymorphic models below a paginated root load each row as its discriminator's class."""
    data = await _data(
        any_async_query,
        """
        {
            garages(limit: 1, offset: 1) {
                id
                vehicles(limit: 2, offset: 1) { id }
                cars { doors }
                bikes { name garage { id } }
            }
        }
        """,
    )
    assert data == {
        "garages": [
            {
                "id": 2,
                "vehicles": _vehicles(7, 8, keys=("id",)),
                "cars": _vehicles(6, keys=("doors",)),
                "bikes": [{"name": "Tandem", "garage": {"id": 2}}, {"name": "Cruiser", "garage": {"id": 2}}],
            }
        ]
    }
    _assert_classes(loaded_vehicles)
    assert query_tracker.query_count == 1
