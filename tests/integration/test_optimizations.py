from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest
from strawchemy import StrawchemyAsyncRepository, StrawchemySyncRepository

import strawberry
from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker
from .types import SQLDataTypesContainerFilter, SQLDataTypesContainerOrderBy, SQLDataTypesContainerType, strawchemy

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

pytestmark = [pytest.mark.integration]


@strawberry.type
class AsyncQuery:
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        repository_type=StrawchemyAsyncRepository,
        filter_input=SQLDataTypesContainerFilter,
        order_by=SQLDataTypesContainerOrderBy,
    )


@strawberry.type
class SyncQuery:
    containers: list[SQLDataTypesContainerType] = strawchemy.field(
        repository_type=StrawchemySyncRepository,
        filter_input=SQLDataTypesContainerFilter,
        order_by=SQLDataTypesContainerOrderBy,
    )


@pytest.fixture
def sync_query() -> type[SyncQuery]:
    return SyncQuery


@pytest.fixture
def async_query() -> type[AsyncQuery]:
    return AsyncQuery


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
        {
            containers(orderBy: { dataTypesAggregate: { count: ASC } }) {
                dataTypesAggregate {
                    count
                }
            }
        }
        """,
            id="output-order-by",
        ),
        pytest.param(
            """
        {
            containers(filter: { dataTypesAggregate: { count: { predicate: { gt: 0 } } } }) {
                dataTypesAggregate {
                    count
                }
            }
        }
        """,
            id="output-filter",
        ),
        pytest.param(
            """
        {
            containers(
                filter: { dataTypesAggregate: { count: { predicate: { gt: 0 } } } },
                orderBy: { dataTypesAggregate: { avg: { floatCol: ASC } } }
            ) {
                dataTypes {
                    id
                }
            }
        }
        """,
            id="filter-order-by",
        ),
        pytest.param(
            """
        {
            containers(
                filter: { dataTypesAggregate: { avg: { arguments: [floatCol] predicate: { gt: 0 } } } },
                orderBy: { dataTypesAggregate: { avg: { floatCol: ASC } } }
            ) {
                dataTypes {
                    id
                }
            }
        }
        """,
            id="filter-order-by-same-aggregation",
        ),
        pytest.param(
            """
        {
            containers {
                dataTypesAggregate {
                    sum {
                        intCol
                        floatCol
                        decimalCol
                    }
                }
            }
        }
        """,
            id="output-multiple-aggregations",
        ),
        pytest.param(
            """
        {
            containers(
                filter: {
                    dataTypesAggregate: {
                        sum: { arguments: [intCol], predicate: { gt: 0 } },
                        avg: { arguments: [floatCol], predicate: { gt: 0 } }
                    }
                }
            ) {
                dataTypes {
                    id
                }
            }
        }
        """,
            id="filter-multiple-aggregations",
        ),
        pytest.param(
            """
        {
            containers(
                orderBy: { dataTypesAggregate: { sum: { intCol: ASC }, avg: { floatCol: ASC } } }
            ) {
                dataTypes {
                    id
                }
            }
        }
        """,
            id="order-by-multiple-aggregations",
        ),
    ],
)
async def test_aggregation_computation_is_reused(
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker
) -> None:
    """Test that aggregation computation is reused when filtering and ordering by the same aggregation."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data

    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_str.count("JOIN LATERAL (") == 1


@pytest.mark.parametrize(
    ("query", "rewrite"),
    [
        pytest.param(
            """
                    {
                        containers(filter: { dataTypes: { intCol: { gt: 1 } } }) {
                            dataTypes {
                                intCol
                            }
                        }
                    }
                """,
            True,
            id="join-rewrite",
        ),
        pytest.param(
            """
                    {
                        containers(filter: { createdAt: { gt: "1220-01-01T00:00:00+00:00" } }) {
                            dataTypes {
                                intCol
                            }
                        }
                    }
                """,
            False,
            id="no-join-rewrite",
        ),
    ],
)
@pytest.mark.snapshot
async def test_inner_join_rewriting(
    query: str, rewrite: bool, any_query: AnyQueryExecutor, query_tracker: QueryTracker, sql_snapshot: SnapshotAssertion
) -> None:
    """Test that if WHERE condition only references columns from the null-supplyign side of the join, use an inner join."""
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot

    if rewrite:
        assert "LEFT OUTER JOIN" not in query_tracker[0].statement_str
        assert query_tracker[0].statement_str.count("JOIN") == 1
    else:
        assert query_tracker[0].statement_str.count("LEFT OUTER JOIN") == 1
