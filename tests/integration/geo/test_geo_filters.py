from __future__ import annotations

import pytest

pytest.importorskip("geoalchemy2", reason="geoalchemy2 is not installed")


from typing import TYPE_CHECKING, Any

import strawberry
from sqlalchemy import Executable, Insert, MetaData, insert, text

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.geo.models import GeoModel, geo_metadata
from tests.integration.geo.utils import GEO_DATA, invert_wkt_coordinates
from tests.integration.utils import to_graphql_representation
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from pytest_databases.docker.postgres import PostgresService
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy
    from strawchemy.typing import SupportedDialect
    from tests.integration.typing import RawRecordData


pytestmark = [pytest.mark.integration, pytest.mark.geo, pytest.mark.extras]

_GEO_FIELDS = ["point", "line_string", "polygon", "multi_point", "multi_polygon", "geometry"]

_GEO_ROWS: RawRecordData = GEO_DATA
# MySQL stores coordinates as (latitude, longitude), so its rows carry the flipped axes.
_GEO_ROWS_FLIPPED: RawRecordData = [
    {key: value if key == "id" or value is None else invert_wkt_coordinates(str(value)) for key, value in row.items()}
    for row in _GEO_ROWS
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(GeoModel, include=["id", *_GEO_FIELDS])
    class GeoFieldsType: ...

    @strawchemy.filter(GeoModel, include=[*_GEO_FIELDS])
    class GeoFieldsFilter: ...

    @strawberry.type
    class Query:
        geo_field: list[GeoFieldsType] = strawchemy.field(filter_input=GeoFieldsFilter)

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    if dialect not in {"postgresql", "mysql"}:
        pytest.skip(f"Geo tests can't be run on this dialect: {dialect}")
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def metadata() -> MetaData:
    return geo_metadata


@pytest.fixture
def postgres_database_service(namespaced_postgis_service: PostgresService) -> PostgresService:
    return namespaced_postgis_service


@pytest.fixture
def before_create_all_statements(dialect: SupportedDialect) -> list[Executable]:
    if dialect == "postgresql":
        return [text("CREATE EXTENSION IF NOT EXISTS postgis")]
    return []


@pytest.fixture
def geo_rows(dialect: SupportedDialect) -> RawRecordData:
    return _GEO_ROWS_FLIPPED if dialect == "mysql" else _GEO_ROWS


@pytest.fixture
def seed_insert_statements(geo_rows: RawRecordData) -> list[Insert]:
    return [insert(GeoModel).values(geo_rows)]


@pytest.mark.snapshot
async def test_no_filtering(
    any_async_query: AnyQueryExecutor,
    geo_rows: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that querying without filters returns all records."""
    result = await maybe_async(any_async_query("{ geoField { id } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(geo_rows)
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.parametrize(
    ("field_name", "geometry", "expected_ids"),
    [
        pytest.param("polygon", {"type": "Point", "coordinates": [0.5, 0.5]}, [0], id="point-within-polygon"),
        pytest.param("multiPolygon", {"type": "Point", "coordinates": [2.5, 2.5]}, [0], id="point-within-multipolygon"),
        pytest.param("geometry", {"type": "Point", "coordinates": [5, 5]}, [0], id="point-equals-geometry-point"),
    ],
)
@pytest.mark.snapshot
async def test_contains_geometry(
    field_name: str,
    geometry: dict[str, Any],
    expected_ids: list[int],
    any_async_query: AnyQueryExecutor,
    geo_rows: RawRecordData,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["geoField"][i]["id"] == geo_rows[expected_id]["id"]
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
    any_async_query: AnyQueryExecutor,
    geo_rows: RawRecordData,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == len(expected_ids)
    for i, expected_id in enumerate(expected_ids):
        assert result.data["geoField"][i]["id"] == geo_rows[expected_id]["id"]
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_is_null(
    any_async_query: AnyQueryExecutor,
    geo_rows: RawRecordData,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
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
    result = await maybe_async(any_async_query(query))
    assert not result.errors
    assert result.data
    assert len(result.data["geoField"]) == 1
    assert result.data["geoField"][0]["id"] == geo_rows[1]["id"]
    assert result.data["geoField"][0]["point"] is None
    # Verify SQL query
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


async def test_not_is_null(any_async_query: AnyQueryExecutor, geo_rows: RawRecordData) -> None:
    result = await maybe_async(any_async_query("{ geoField(filter: { _not: { point: { isNull: true } } }) { id } }"))
    assert not result.errors
    assert result.data

    assert sorted(row["id"] for row in result.data["geoField"]) == sorted(
        to_graphql_representation(row["id"], "output") for row in geo_rows if row["point"] is not None
    )


@pytest.mark.parametrize("operator", ["isNull", "containsGeometry", "withinGeometry"])
@pytest.mark.parametrize("negated", [pytest.param(False, id="plain"), pytest.param(True, id="not")])
async def test_null_operator_is_ignored(
    operator: str, negated: bool, any_async_query: AnyQueryExecutor, geo_rows: RawRecordData
) -> None:
    """Test that a geo operator set to null is ignored, directly and under ``_not``."""
    dto_filter = f"{{ point: {{ {operator}: null }} }}"
    if negated:
        dto_filter = f"{{ _not: {dto_filter} }}"
    result = await maybe_async(any_async_query(f"{{ geoField(filter: {dto_filter}) {{ id }} }}"))
    assert not result.errors
    assert result.data

    assert sorted(row["id"] for row in result.data["geoField"]) == sorted(
        to_graphql_representation(row["id"], "output") for row in geo_rows
    )
