from __future__ import annotations

import pytest

pytest.importorskip("geoalchemy2", reason="geoalchemy2 is not installed")


from typing import TYPE_CHECKING, Any

from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import Executable, Insert, MetaData, insert, text
from tests.integration.fixtures import QueryTracker
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .models import GeoModel, geo_metadata
from .types import GeoFieldsFilter, GeoFieldsType, strawchemy

if TYPE_CHECKING:
    from pytest_databases.docker.postgres import PostgresService

    from syrupy.assertion import SnapshotAssertion
    from tests.integration.typing import RawRecordData


pytestmark = [pytest.mark.integration, pytest.mark.geo]


@pytest.fixture
def metadata() -> MetaData:
    return geo_metadata


@pytest.fixture
def database_service(postgis_service: PostgresService) -> PostgresService:
    return postgis_service


@pytest.fixture
def before_create_all_statements() -> list[Executable]:
    return [text("CREATE EXTENSION IF NOT EXISTS postgis")]


@strawberry.type
class AsyncQuery:
    geo_field: list[GeoFieldsType] = strawchemy.field(
        filter_input=GeoFieldsFilter, repository_type=StrawchemyAsyncRepository
    )


@strawberry.type
class SyncQuery:
    geo_field: list[GeoFieldsType] = strawchemy.field(
        filter_input=GeoFieldsFilter, repository_type=StrawchemySyncRepository
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.fixture
def seed_insert_statements(raw_geo: RawRecordData) -> list[Insert]:
    return [insert(GeoModel).values(raw_geo)]


@pytest.mark.snapshot
async def test_no_filtering(
    any_query: AnyQueryExecutor, raw_geo: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that querying without filters returns all records."""
    result = await maybe_async(any_query("{ geoField { id } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(raw_geo)
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "geometry", "expected_ids"),
    [
        pytest.param("polygon", {"type": "Point", "coordinates": [0.5, 0.5]}, [0, 3], id="point-within-polygon"),
        pytest.param("multiPolygon", {"type": "Point", "coordinates": [3, 3]}, [3], id="point-within-multipolygon"),
        pytest.param("geometry", {"type": "Point", "coordinates": [150, 150]}, [3], id="point-within-geometry-polygon"),
    ],
)
@pytest.mark.snapshot
async def test_contains_geometry(
    field_name: str,
    geometry: dict[str, Any],
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_geo: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the contains_geometry filter.

    This tests that a geometry contains the provided geometry.
    For example, a polygon contains a point if the point is inside the polygon.
    """
    query = f"""
            {{
                geoField(filter: {{ {field_name}: {{ containsGeometry: {to_graphql_representation(geometry, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["geoField"][i]["id"] == raw_geo[expected_id]["id"]
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "geometry", "expected_ids"),
    [
        pytest.param(
            "point",
            {"type": "Polygon", "coordinates": [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]]},
            [0],
            id="point-within-polygon",
        ),
        pytest.param(
            "lineString",
            {"type": "Polygon", "coordinates": [[[0, 0], [0, 3], [3, 3], [3, 0], [0, 0]]]},
            [0],
            id="linestring-within-polygon",
        ),
        pytest.param(
            "multiPoint",
            {
                "coordinates": [
                    [
                        [3.8530909369223423, 3.5077205177229587],
                        [-2.126498556883888, 3.5077205177229587],
                        [-2.126498556883888, -0.8070832671228061],
                        [3.8530909369223423, -0.8070832671228061],
                        [3.8530909369223423, 3.5077205177229587],
                    ]
                ],
                "type": "Polygon",
            },
            [0],
            id="multipoint-within-polygon",
        ),
    ],
)
@pytest.mark.snapshot
async def test_within_geometry(
    field_name: str,
    geometry: dict[str, Any],
    expected_ids: list[int],
    any_query: AnyQueryExecutor,
    raw_geo: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test the within_geometry filter.

    This tests that a geometry is within the provided geometry.
    For example, a point is within a polygon if the point is inside the polygon.
    """
    query = f"""
            {{
                geoField(filter: {{ {field_name}: {{ withinGeometry: {to_graphql_representation(geometry, "input")} }} }}) {{
                    id
                    {field_name}
                }}
            }}
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["geoField"][i]["id"] == raw_geo[expected_id]["id"]
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_is_null(
    any_query: AnyQueryExecutor, raw_geo: RawRecordData, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test the isNull filter for geometry fields."""
    query = """
            {
                geoField(filter: { point: { isNull: true } }) {
                    id
                    point
                }
            }
    """
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == 1
    assert result.data["geoField"][0]["id"] == raw_geo[1]["id"]
    assert result.data["geoField"][0]["point"] is None
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
