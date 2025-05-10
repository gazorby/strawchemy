from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING

import pytest

from tests.typing import AnyQueryExecutor
from tests.utils import maybe_async

from .fixtures import QueryTracker

if TYPE_CHECKING:
    from strawchemy.typing import SupportedDialect

    from syrupy.assertion import SnapshotAssertion

pytestmark = [pytest.mark.integration]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
        {
            colors(orderBy: { fruitsAggregate: { count: ASC } }) {
                fruitsAggregate {
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
            colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } }) {
                fruitsAggregate {
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
            colors(
                filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } },
                orderBy: { fruitsAggregate: { avg: { waterPercent: ASC } } }
            ) {
                fruits {
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
            colors(
                filter: { fruitsAggregate: { avg: { arguments: [waterPercent] predicate: { gt: 0 } } } },
                orderBy: { fruitsAggregate: { avg: { waterPercent: ASC } } }
            ) {
                fruits {
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
            colors {
                fruitsAggregate {
                    max {
                        sweetness
                        waterPercent
                        name
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
            colors(
                filter: {
                    fruitsAggregate: {
                        sum: { arguments: [sweetness], predicate: { gt: 0 } },
                        avg: { arguments: [waterPercent], predicate: { gt: 0 } }
                    }
                }
            ) {
                fruits {
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
            colors(
                orderBy: { fruitsAggregate: { sum: { sweetness: ASC }, avg: { waterPercent: ASC } } }
            ) {
                fruits {
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
    query: str, any_query: AnyQueryExecutor, query_tracker: QueryTracker, dialect: SupportedDialect
) -> None:
    """Test that aggregation computation is reused when filtering and ordering by the same aggregation."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = await maybe_async(any_query(query))

    assert not result.errors
    assert result.data

    assert query_tracker.query_count == 1
    if dialect == "postgresql":
        assert query_tracker[0].statement_str.count("JOIN LATERAL (") == 1
    else:
        assert query_tracker[0].statement_str.count("aggregation_0 AS ") == 1
        assert not re.match(r" aggregation_[1-9]\d* AS $", query_tracker[0].statement_str)


@pytest.mark.parametrize(
    ("query", "inner_join_expected"),
    [
        pytest.param(
            """
                    {
                        colors(filter: { fruits: { sweetness: { gt: 1 } } }) {
                            fruits {
                                sweetness
                            }
                        }
                    }
                """,
            True,
            id="inner-join-rewrite",
        ),
        pytest.param(
            """
                    {
                        colors(filter: { createdAt: { gt: "1220-01-01T00:00:00" } }) {
                            fruits {
                                sweetness
                            }
                        }
                    }
                """,
            False,
            id="no-inner-join-rewrite",
        ),
    ],
)
@pytest.mark.snapshot
async def test_inner_join_rewriting(
    query: str,
    inner_join_expected: bool,
    any_query: AnyQueryExecutor,
    query_tracker: QueryTracker,
    sql_snapshot: SnapshotAssertion,
) -> None:
    """Test that if WHERE condition only references columns from the null-supplying side of the join, use an inner join."""
    result = await maybe_async(any_query(query))
    assert not result.errors
    assert result.data
    assert query_tracker.query_count == 1
    assert query_tracker[0].statement_formatted == sql_snapshot

    if inner_join_expected:
        assert "LEFT OUTER JOIN" not in query_tracker[0].statement_str
        assert query_tracker[0].statement_str.count("JOIN") == 1
    else:
        assert query_tracker[0].statement_str.count("LEFT OUTER JOIN") == 1
