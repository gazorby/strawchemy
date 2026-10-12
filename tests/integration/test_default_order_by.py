from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import strawberry
from sqlalchemy import Insert, insert

from tests.integration.fixtures import Operations, QueryTracker, SchemaTypes
from tests.integration.models import Color, Fruit, FruitFarm
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

    from strawchemy import Strawchemy, StrawchemyConfig
    from strawchemy.typing import SupportedDialect

pytestmark = [pytest.mark.integration]

_COLORS: list[dict[str, Any]] = [{"id": 1, "name": "Red"}, {"id": 2, "name": "Yellow"}]
# Ids do not follow name order, and Lemon/Banana tie on sweetness, so name ordering, the primary key tiebreaker and
# the secondary default column each give a different result.
_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple", "sweetness": 4, "water_percent": 0.84, "color_id": 1},
    {"id": 2, "name": "Cherry", "sweetness": 9, "water_percent": 0.93, "color_id": 1},
    {"id": 3, "name": "Lemon", "sweetness": 2, "water_percent": 0.88, "color_id": 2},
    {"id": 4, "name": "Banana", "sweetness": 2, "water_percent": 0.75, "color_id": 2},
]
_FRUIT_FARMS: list[dict[str, Any]] = [
    {"id": 1, "name": "Apple farm", "fruit_id": 1},
    {"id": 2, "name": "Apple farm 2", "fruit_id": 1},
    {"id": 3, "name": "Apple farm 3", "fruit_id": 1},
    {"id": 4, "name": "Cherry farm", "fruit_id": 2},
]


def _schema(strawchemy: Strawchemy) -> Operations:
    @strawchemy.type(Fruit, include=["id", "name", "sweetness"], override=True)
    class FruitType: ...

    @strawchemy.type(Fruit, include=["id", "name", "farms"], paginate="all")
    class FruitWithFarmsType: ...

    @strawchemy.type(Color, include=["id", "name", "fruits"], paginate="all")
    class ColorWithFruitsType: ...

    @strawchemy.order(Fruit, include=["name"])
    class FruitOrderBy: ...

    @strawchemy.distinct_on(Fruit, include=["name"])
    class FruitDistinctOn: ...

    @strawberry.type
    class Query:
        fruits_default_order: list[FruitType] = strawchemy.field(default_order_by=Fruit.name.asc(), pagination=True)
        fruits_default_order_no_pagination: list[FruitType] = strawchemy.field(
            default_order_by=Fruit.name.asc(), order_by_input=FruitOrderBy
        )
        fruits_default_order_multi: list[FruitType] = strawchemy.field(
            default_order_by=[Fruit.sweetness.desc(), Fruit.name.asc()]
        )
        fruits_default_order_distinct: list[FruitType] = strawchemy.field(
            default_order_by=Fruit.name.asc(), distinct_on=FruitDistinctOn
        )
        fruits_default_order_sweetness: list[FruitWithFarmsType] = strawchemy.field(
            default_order_by=Fruit.sweetness.desc()
        )
        colors_default_order: list[ColorWithFruitsType] = strawchemy.field(default_order_by=Color.name.desc())

    return Operations(query=Query)


@pytest.fixture
def schema(dialect: SupportedDialect) -> SchemaTypes:
    return SchemaTypes.build(dialect, _schema)


@pytest.fixture
def seed_insert_statements() -> list[Insert]:
    return [insert(Color).values(_COLORS), insert(Fruit).values(_FRUITS), insert(FruitFarm).values(_FRUIT_FARMS)]


async def test_default_order_by_applied_when_no_client_order(any_async_query: AnyQueryExecutor) -> None:
    """Default ordering by name ASC is applied when the client sends no orderBy.

    The default-ordered result is compared against an explicit ``orderBy: { name: ASC }``
    query issued to the same database, so the assertion is independent of the database's
    text collation (which differs between sqlite's binary ordering and Postgres/MySQL
    locale-aware ordering).
    """
    default = await maybe_async(any_async_query("{ fruitsDefaultOrderNoPagination { id name } }"))
    explicit = await maybe_async(
        any_async_query("{ fruitsDefaultOrderNoPagination(orderBy: { name: ASC }) { id name } }")
    )
    assert not default.errors
    assert not explicit.errors
    assert default.data
    assert explicit.data
    assert len(default.data["fruitsDefaultOrderNoPagination"]) == len(_FRUITS)
    # No client order falls back to default_order_by (name ASC), matching explicit name ASC.
    assert default.data["fruitsDefaultOrderNoPagination"] == explicit.data["fruitsDefaultOrderNoPagination"]


async def test_client_order_overrides_default(any_async_query: AnyQueryExecutor) -> None:
    """A client orderBy fully overrides default_order_by.

    Compares the descending result against the reverse of the ascending result (names are
    unique in the fixture), keeping the assertion independent of database text collation.
    """
    asc = await maybe_async(any_async_query("{ fruitsDefaultOrderNoPagination(orderBy: { name: ASC }) { id name } }"))
    desc = await maybe_async(any_async_query("{ fruitsDefaultOrderNoPagination(orderBy: { name: DESC }) { id name } }"))
    assert not asc.errors
    assert not desc.errors
    assert asc.data
    assert desc.data
    assert len(desc.data["fruitsDefaultOrderNoPagination"]) == len(_FRUITS)
    asc_names = [row["name"] for row in asc.data["fruitsDefaultOrderNoPagination"]]
    desc_names = [row["name"] for row in desc.data["fruitsDefaultOrderNoPagination"]]
    # Client DESC ordering is honored over the default ASC, producing the reverse order.
    assert desc_names == list(reversed(asc_names))


@pytest.mark.snapshot
async def test_default_order_with_pk_tiebreaker(
    any_async_query: AnyQueryExecutor,
    config: StrawchemyConfig,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """With deterministic_ordering=True the PK is appended after the default column."""
    # True is the StrawchemyConfig default
    config.deterministic_ordering = True
    result = await maybe_async(any_async_query("{ fruitsDefaultOrderNoPagination { id name } }"))
    assert not result.errors
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_without_pk_tiebreaker(
    any_async_query: AnyQueryExecutor,
    config: StrawchemyConfig,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """With deterministic_ordering=False only the default column is emitted (no PK)."""
    config.deterministic_ordering = False
    result = await maybe_async(any_async_query("{ fruitsDefaultOrderNoPagination { id name } }"))
    assert not result.errors
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_under_pagination(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Default ordering is adapted to the subquery alias when paginating (limit/offset)."""
    result = await maybe_async(any_async_query("{ fruitsDefaultOrder(limit: 2, offset: 1) { id name } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["fruitsDefaultOrder"]) == 2
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_multi_column(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Multi-column default_order_by list is applied: sweetness DESC, name ASC, then PK tiebreaker."""
    result = await maybe_async(any_async_query("{ fruitsDefaultOrderMulti { id name sweetness } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["fruitsDefaultOrderMulti"]) == len(_FRUITS)
    expected_names = [row["name"] for row in sorted(_FRUITS, key=lambda r: (-r["sweetness"], r["name"]))]
    assert [row["name"] for row in result.data["fruitsDefaultOrderMulti"]] == expected_names
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_with_distinct_on(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """distinct_on combined with default_order_by uses the default ordering inside the RANK window."""
    result = await maybe_async(any_async_query("{ fruitsDefaultOrderDistinct(distinctOn: [name]) { id name } }"))
    assert not result.errors
    assert result.data
    assert len(result.data["fruitsDefaultOrderDistinct"]) > 0
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_not_applied_to_nested_same_named_column(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """A root default ordering on ``name`` leaves nested rows ordered by their primary key, not their own ``name``."""
    result = await maybe_async(any_async_query("{ colorsDefaultOrder { name fruits(limit: 1) { id name } } }"))
    assert not result.errors
    assert result.data
    red = next(color for color in result.data["colorsDefaultOrder"] if color["name"] == "Red")
    assert [fruit["name"] for fruit in red["fruits"]] == ["Apple"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot


@pytest.mark.snapshot
async def test_default_order_not_applied_to_nested_missing_column(
    any_async_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """A root default ordering on a column the nested model lacks does not fail the nested plan."""
    result = await maybe_async(any_async_query("{ fruitsDefaultOrderSweetness { name farms(limit: 10) { name } } }"))
    assert not result.errors
    assert result.data
    apple = next(fruit for fruit in result.data["fruitsDefaultOrderSweetness"] if fruit["name"] == "Apple")
    assert [farm["name"] for farm in apple["farms"]] == ["Apple farm", "Apple farm 2", "Apple farm 3"]
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot
