from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote
from uuid import uuid4

import pytest
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from pytest_databases.docker.postgres import _provide_postgres_service
from shapely import to_geojson
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from sqlalchemy import Executable, Insert, MetaData, insert, text
from tests.integration.fixtures import QueryTracker
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .models import GeoModel, geo_metadata
from .types import GeoFieldsFilter, GeoFieldsType, strawchemy

if TYPE_CHECKING:
    from collections.abc import Generator

    from geoalchemy2 import WKBElement
    from pytest_databases._service import DockerService
    from pytest_databases.docker.postgres import PostgresService
    from pytest_databases.types import XdistIsolationLevel

    from syrupy.assertion import SnapshotAssertion
    from tests.integration.typing import RawRecordData

pytestmark = [pytest.mark.integration, pytest.mark.geo]


_geo_data = [
    # Complete record with all geometry types
    {
        "id": str(uuid4()),
        "point_required": "POINT(0 0)",  # Origin point
        "point": "POINT(1 1)",  # Simple point
        "line_string": "LINESTRING(0 0, 1 1, 2 2)",  # Simple line with 3 points
        "polygon": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",  # Simple square
        "multi_point": "MULTIPOINT((0 0), (1 1), (2 2))",  # 3 points
        "multi_line_string": "MULTILINESTRING((0 0, 1 1), (2 2, 3 3))",  # 2 lines
        "multi_polygon": "MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)), ((2 2, 2 3, 3 3, 3 2, 2 2)))",  # 2 squares
        "geometry": "POINT(5 5)",  # Using point as generic geometry
    },
    # Record with only required fields
    {
        "id": str(uuid4()),
        "point_required": "POINT(10 20)",  # Required point
        "point": None,
        "line_string": None,
        "polygon": None,
        "multi_point": None,
        "multi_line_string": None,
        "multi_polygon": None,
        "geometry": None,
    },
    # Record with complex geometries
    {
        "id": str(uuid4()),
        "point_required": "POINT(45.5 -122.6)",  # Real-world coordinates (Portland, OR)
        "point": "POINT(-74.0060 40.7128)",  # New York City
        "line_string": "LINESTRING(-122.4194 37.7749, -118.2437 34.0522, -74.0060 40.7128)",  # SF to LA to NYC
        "polygon": "POLYGON((-122.4194 37.7749, -122.4194 37.8, -122.4 37.8, -122.4 37.7749, -122.4194 37.7749))",  # Area in SF
        "multi_point": "MULTIPOINT((-122.4194 37.7749), (-118.2437 34.0522), (-74.0060 40.7128))",  # Major US cities
        "multi_line_string": "MULTILINESTRING((-122.4194 37.7749, -118.2437 34.0522), (-118.2437 34.0522, -74.0060 40.7128))",  # Route segments
        "multi_polygon": "MULTIPOLYGON(((-122.42 37.78, -122.42 37.8, -122.4 37.8, -122.4 37.78, -122.42 37.78)), ((-118.25 34.05, -118.25 34.06, -118.24 34.06, -118.24 34.05, -118.25 34.05)))",  # Areas in SF and LA
        "geometry": "LINESTRING(-122.4194 37.7749, -74.0060 40.7128)",  # Direct SF to NYC
    },
    # Record with different geometry types
    {
        "id": str(uuid4()),
        "point_required": "POINT(100 200)",
        "point": "POINT(200 300)",
        "line_string": "LINESTRING(100 100, 200 200, 300 300, 400 400)",  # Longer line
        "polygon": "POLYGON((0 0, 0 10, 10 10, 10 0, 0 0), (2 2, 2 8, 8 8, 8 2, 2 2))",  # Polygon with hole
        "multi_point": "MULTIPOINT((10 10), (20 20), (30 30), (40 40), (50 50))",  # 5 points
        "multi_line_string": "MULTILINESTRING((10 10, 20 20), (30 30, 40 40), (50 50, 60 60))",  # 3 lines
        "multi_polygon": "MULTIPOLYGON(((0 0, 0 5, 5 5, 5 0, 0 0)), ((10 10, 10 15, 15 15, 15 10, 10 10)), ((20 20, 20 25, 25 25, 25 20, 20 20)))",  # 3 squares
        "geometry": "POLYGON((100 100, 100 200, 200 200, 200 100, 100 100))",  # Using polygon as geometry
    },
]


def _element_to_geojson_io_url(element: WKBElement | WKTElement | str) -> str:
    base_url = "https://geojson.io/#data=data:application/json,"
    if isinstance(element, str):
        element = WKTElement(element)
    geojson = to_geojson(to_shape(element))
    return f"{base_url}{quote(geojson)}"


def geo_data_visualization_urls() -> None:
    data = [
        {key: _element_to_geojson_io_url(value) for key, value in row.items() if key != "id" and value is not None}
        for row in _geo_data
    ]
    print(json.dumps(data, indent=2))  # noqa: T201


def _to_graphql_representation(value: Any, mode: Literal["input", "output"]) -> Any:
    """Convert Python values to their GraphQL string representation.

    This function transforms various Python data types into their appropriate
    GraphQL representation, with different handling based on whether the value
    is being used as input to a GraphQL query or as output from a GraphQL query.

    Args:
        value: The Python value to convert to a GraphQL representation.
            Supported types include:
            - Basic types (str, int, float, bool)
            - GeoJSON objects (as Python dictionaries)
        mode: Determines the conversion format:
            - "input": For values used in GraphQL query filters/arguments
            - "output": For values expected in GraphQL query results

    Returns:
        The GraphQL representation of the input value
    """
    if isinstance(value, dict) and "type" in value and "coordinates" in value:
        # Handle GeoJSON dictionary
        if mode == "input":
            return re.sub(r'"([^"]+)":', r"\g<1>:", json.dumps(value))
        return value

    return value


@pytest.fixture
def metadata() -> MetaData:
    return geo_metadata


@pytest.fixture(autouse=False, scope="session")
def postgis_service(
    docker_service: DockerService, xdist_postgres_isolation_level: XdistIsolationLevel
) -> Generator[PostgresService, None, None]:
    with _provide_postgres_service(
        docker_service,
        image="postgis/postgis:17-3.5",
        name="postgis-17",
        xdist_postgres_isolate=xdist_postgres_isolation_level,
    ) as service:
        yield service


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
def raw_geo() -> RawRecordData:
    return _geo_data


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
                geoField(filter: {{ {field_name}: {{ containsGeometry: {_to_graphql_representation(geometry, "input")} }} }}) {{
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
                geoField(filter: {{ {field_name}: {{ withinGeometry: {_to_graphql_representation(geometry, "input")} }} }}) {{
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
