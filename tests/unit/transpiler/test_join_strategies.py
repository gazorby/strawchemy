"""Tests for join strategy selection and construction."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import pytest
from inline_snapshot import snapshot
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SAWarning
from sqlalchemy.sql.compiler import FROM_LINTING

from strawchemy.config.databases import DatabaseFeatures
from strawchemy.transpiler._strategies import (
    CteJoinStrategy,
    LateralJoinStrategy,
    select_join_strategy,
)
from tests.unit.schemas.secondary_table import schema as secondary_table_schema
from tests.unit.utils import DialectContext
from tests.utils import format_sql

if TYPE_CHECKING:
    from sqlalchemy import Select


def _linted_sql(statement: Select[Any]) -> str:
    """Compiles for postgres with the FROM linter on, so a cartesian product raises.

    Args:
        statement: The statement to compile.

    Raises:
        SAWarning: If the compiled statement has unrelated FROM elements.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", category=SAWarning)
        return format_sql(str(statement.compile(dialect=postgresql.dialect(), linting=FROM_LINTING)))


def test_select_join_strategy_returns_lateral_when_supported() -> None:
    """A lateral-capable dialect selects the lateral strategy."""
    db_features = DatabaseFeatures.new("postgresql")
    assert db_features.supports_lateral is True
    strategy = select_join_strategy(db_features)
    assert isinstance(strategy, LateralJoinStrategy)
    assert callable(strategy.relation_join)


def test_select_join_strategy_returns_cte_when_not_supported() -> None:
    """A dialect without lateral selects the CTE strategy."""
    db_features = DatabaseFeatures.new("sqlite")
    assert db_features.supports_lateral is False
    strategy = select_join_strategy(db_features)
    assert isinstance(strategy, CteJoinStrategy)
    assert callable(strategy.relation_join)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "{ users { id departmentsAggregate { count } } }",
            snapshot(
                [
                    'SELECT "user".id,',
                    "       anon_1.count_1",
                    '  FROM "user" AS "user"',
                    "  JOIN LATERAL (",
                    "        SELECT count(*) AS count_1",
                    "          FROM user_department_join_table AS user_department_join_table_1",
                    "          JOIN department AS department_1",
                    "            ON department_1.id = user_department_join_table_1.department_id",
                    '         WHERE "user".id = user_department_join_table_1.user_id',
                    "       ) AS anon_1",
                    "    ON TRUE",
                    ' ORDER BY "user".id ASC',
                ]
            ),
            id="aggregation",
        ),
        pytest.param(
            "{ users { id departments(limit: 2) { id name } } }",
            snapshot(
                [
                    "SELECT anon_1.name,",
                    "       anon_1.id,",
                    '       "user".id AS id_1',
                    '  FROM "user" AS "user"',
                    "  LEFT OUTER JOIN LATERAL (",
                    "        SELECT department_1.id AS id,",
                    "               department_1.name AS name",
                    "          FROM user_department_join_table AS user_department_join_table_1",
                    "          JOIN department AS department_1",
                    "            ON department_1.id = user_department_join_table_1.department_id",
                    '         WHERE "user".id = user_department_join_table_1.user_id',
                    "         ORDER BY department_1.id ASC",
                    "         LIMIT %(param_1)s",
                    "       ) AS anon_1",
                    "    ON TRUE",
                    ' ORDER BY "user".id ASC,',
                    "          anon_1.id ASC",
                ]
            ),
            id="relation",
        ),
    ],
)
@pytest.mark.inline_snapshot
def test_secondary_lateral_joins_the_secondary_table(
    query: str, expected: list[str], captured_statements: list[Select[Any]]
) -> None:
    """A secondary-table lateral joins the secondary table instead of correlating it in WHERE."""
    result = secondary_table_schema.execute_sync(query, context_value=DialectContext("postgresql"))

    assert not result.errors
    assert _linted_sql(captured_statements[0]).splitlines() == expected
