"""DB-free unit tests for transpiler SQL optimizations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from inline_snapshot import snapshot

from tests.unit.schemas.optimizations import schema
from tests.unit.utils import SQLA_DIALECTS, DialectContext
from tests.utils import format_sql

if TYPE_CHECKING:
    from sqlalchemy import Select

# Module-level snapshots storing every (query, dialect) combination; required because a single
# ``snapshot()`` literal cannot be a param under stacked parametrize (cross-product).

AGGREGATION_SQL = snapshot(
    {
        "output-order-by-postgresql": [
            "SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT count(*) AS count_1",
            "          FROM fruit AS fruit_1",
            "         WHERE color.id = fruit_1.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            " ORDER BY anon_1.count_1 ASC",
        ],
        "output-order-by-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " ORDER BY anon_1.count_1 ASC",
        ],
        "output-order-by-mysql": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " ORDER BY anon_1.count_1 ASC",
        ],
        "output-filter-postgresql": [
            "SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT count(*) AS count_1",
            "          FROM fruit AS fruit_1",
            "         WHERE color.id = fruit_1.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            " WHERE anon_1.count_1 > %(param_1)s",
            " ORDER BY color.id ASC",
        ],
        "output-filter-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " WHERE anon_1.count_1 > ?",
            " ORDER BY color.id ASC",
        ],
        "output-filter-mysql": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.count_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " WHERE anon_1.count_1 > %s",
            " ORDER BY color.id ASC",
        ],
        "filter-order-by-postgresql": [
            "SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT count(*) AS count_1,",
            "               avg(fruit_2.sweetness) AS avg_1",
            "          FROM fruit AS fruit_2",
            "         WHERE color.id = fruit_2.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.count_1 > %(param_1)s",
            " ORDER BY anon_1.count_1 ASC,",
            "          anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-order-by-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               avg(fruit_2.sweetness) AS avg_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.count_1 > ?",
            " ORDER BY anon_1.count_1 ASC,",
            "          anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-order-by-mysql": [
            "WITH anon_1 AS (",
            "        SELECT count(*) AS count_1,",
            "               avg(fruit_2.sweetness) AS avg_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.count_1 > %s",
            " ORDER BY anon_1.count_1 ASC,",
            "          anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-order-by-same-aggregation-postgresql": [
            "SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1",
            "          FROM fruit AS fruit_2",
            "         WHERE color.id = fruit_2.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > %(param_1)s",
            " ORDER BY anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-order-by-same-aggregation-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > ?",
            " ORDER BY anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-order-by-same-aggregation-mysql": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > %s",
            " ORDER BY anon_1.avg_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "output-multiple-aggregations-postgresql": [
            "SELECT color.id,",
            "       anon_1.max_1,",
            "       anon_1.max_2",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT max(fruit_1.sweetness) AS max_1,",
            "               max(fruit_1.name) AS max_2",
            "          FROM fruit AS fruit_1",
            "         WHERE color.id = fruit_1.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            " ORDER BY color.id ASC",
        ],
        "output-multiple-aggregations-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT max(fruit_1.sweetness) AS max_1,",
            "               max(fruit_1.name) AS max_2,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.max_1,",
            "       anon_1.max_2",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " ORDER BY color.id ASC",
        ],
        "output-multiple-aggregations-mysql": [
            "WITH anon_1 AS (",
            "        SELECT max(fruit_1.sweetness) AS max_1,",
            "               max(fruit_1.name) AS max_2,",
            "               fruit_1.color_id AS color_id",
            "          FROM fruit AS fruit_1",
            "         WHERE fruit_1.color_id IS NOT NULL",
            "         GROUP BY fruit_1.color_id",
            "       ) SELECT color.id,",
            "       anon_1.max_1,",
            "       anon_1.max_2",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            " ORDER BY color.id ASC",
        ],
        "filter-multiple-aggregations-postgresql": [
            "SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1",
            "          FROM fruit AS fruit_2",
            "         WHERE color.id = fruit_2.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > %(param_1)s",
            "   AND anon_1.sum_1 > %(param_2)s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-multiple-aggregations-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > ?",
            "   AND anon_1.sum_1 > ?",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "filter-multiple-aggregations-mysql": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE anon_1.avg_1 > %s",
            "   AND anon_1.sum_1 > %s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "order-by-multiple-aggregations-postgresql": [
            "SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN LATERAL (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1",
            "          FROM fruit AS fruit_2",
            "         WHERE color.id = fruit_2.color_id",
            "       ) AS anon_1",
            "    ON TRUE",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " ORDER BY anon_1.avg_1 ASC,",
            "          anon_1.sum_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "order-by-multiple-aggregations-sqlite": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " ORDER BY anon_1.avg_1 ASC,",
            "          anon_1.sum_1 ASC,",
            "          fruit_1.id ASC",
        ],
        "order-by-multiple-aggregations-mysql": [
            "WITH anon_1 AS (",
            "        SELECT avg(fruit_2.sweetness) AS avg_1,",
            "               sum(fruit_2.sweetness) AS sum_1,",
            "               fruit_2.color_id AS color_id",
            "          FROM fruit AS fruit_2",
            "         WHERE fruit_2.color_id IS NOT NULL",
            "         GROUP BY fruit_2.color_id",
            "       ) SELECT fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            " INNER JOIN anon_1",
            "    ON color.id = anon_1.color_id",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " ORDER BY anon_1.avg_1 ASC,",
            "          anon_1.sum_1 ASC,",
            "          fruit_1.id ASC",
        ],
    }
)

INNER_JOIN_SQL = snapshot(
    {
        "inner-join-rewrite-postgresql": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE fruit_1.sweetness > %(sweetness_1)s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "inner-join-rewrite-sqlite": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE fruit_1.sweetness > ?",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "inner-join-rewrite-mysql": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            " INNER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE fruit_1.sweetness > %s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "no-inner-join-rewrite-postgresql": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE color.name = %(name_1)s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "no-inner-join-rewrite-sqlite": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE color.name = ?",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
        "no-inner-join-rewrite-mysql": [
            "SELECT fruit_1.sweetness,",
            "       fruit_1.id,",
            "       color.id AS id_1",
            "  FROM color AS color",
            "  LEFT OUTER JOIN fruit AS fruit_1",
            "    ON color.id = fruit_1.color_id",
            " WHERE color.name = %s",
            " ORDER BY color.id ASC,",
            "          fruit_1.id ASC",
        ],
    }
)


@pytest.mark.inline_snapshot
@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
@pytest.mark.parametrize(
    "query",
    [
        pytest.param(
            """
            {
                colors(orderBy: { fruitsAggregate: { count: ASC } }) {
                    fruitsAggregate { count }
                }
            }
            """,
            id="output-order-by",
        ),
        pytest.param(
            """
            {
                colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } }) {
                    fruitsAggregate { count }
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
                    orderBy: { fruitsAggregate: { avg: { sweetness: ASC } } }
                ) {
                    fruits { id }
                }
            }
            """,
            id="filter-order-by",
        ),
        pytest.param(
            """
            {
                colors(
                    filter: { fruitsAggregate: { avg: { arguments: [sweetness] predicate: { gt: 0 } } } },
                    orderBy: { fruitsAggregate: { avg: { sweetness: ASC } } }
                ) {
                    fruits { id }
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
                        max { sweetness name }
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
                            avg: { arguments: [sweetness], predicate: { gt: 0 } }
                        }
                    }
                ) {
                    fruits { id }
                }
            }
            """,
            id="filter-multiple-aggregations",
        ),
        pytest.param(
            """
            {
                colors(
                    orderBy: { fruitsAggregate: { sum: { sweetness: ASC }, avg: { sweetness: ASC } } }
                ) {
                    fruits { id }
                }
            }
            """,
            id="order-by-multiple-aggregations",
        ),
    ],
)
def test_aggregation_computation_is_reused(
    query: str, dialect_name: str, captured_statements: list[Select[Any]], request: pytest.FixtureRequest
) -> None:
    """A single query is emitted with the aggregation computation reused (no duplicate subquery).

    Filtering and ordering by the same aggregation share one subquery; distinct aggregations
    each get their own. Verified DB-free by compiling the captured statement per dialect.
    """
    result = schema.execute_sync(query, context_value=DialectContext(dialect_name))  # ty: ignore[invalid-argument-type]

    assert not result.errors
    assert result.data

    assert len(captured_statements) == 1
    compiled = str(captured_statements[0].compile(dialect=SQLA_DIALECTS[dialect_name]))
    assert format_sql(compiled).splitlines() == AGGREGATION_SQL[request.node.callspec.id]


@pytest.mark.inline_snapshot
@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
@pytest.mark.parametrize(
    ("query",),  # noqa: PT006
    [
        pytest.param(
            """
            {
                colors(filter: { fruits: { sweetness: { gt: 1 } } }) {
                    fruits { sweetness }
                }
            }
            """,
            id="inner-join-rewrite",
        ),
        pytest.param(
            """
            {
                colors(filter: { name: { eq: "x" } }) {
                    fruits { sweetness }
                }
            }
            """,
            id="no-inner-join-rewrite",
        ),
    ],
)
def test_inner_join_rewriting(
    query: str, dialect_name: str, captured_statements: list[Select[Any]], request: pytest.FixtureRequest
) -> None:
    """A WHERE that only references the null-supplying side rewrites the LEFT OUTER JOIN to INNER.

    When the filter references the parent's own column instead, the outer join is preserved.
    """
    result = schema.execute_sync(query, context_value=DialectContext(dialect_name))  # ty: ignore[invalid-argument-type]

    assert not result.errors
    assert result.data
    assert len(captured_statements) == 1

    statement_str = str(captured_statements[0].compile(dialect=SQLA_DIALECTS[dialect_name]))
    assert format_sql(statement_str).splitlines() == INNER_JOIN_SQL[request.node.callspec.id]
