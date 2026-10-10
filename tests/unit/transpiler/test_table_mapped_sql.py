"""SQL of models mapped onto a ``Table`` through ``__table__`` instead of ``__tablename__``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from inline_snapshot import snapshot

from tests.unit.schemas.table_mapped import schema
from tests.unit.utils import SQLA_DIALECTS, MockContext
from tests.utils import format_sql

if TYPE_CHECKING:
    from sqlalchemy import Select


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param(
            "{ books { title } }",
            snapshot(
                [
                    "SELECT table_mapped_book.id,",
                    "       table_mapped_book.title",
                    "  FROM table_mapped_book AS table_mapped_book",
                    " ORDER BY table_mapped_book.id ASC",
                ]
            ),
            id="root",
        ),
        pytest.param(
            "{ booksPaginated(limit: 2) { title } }",
            snapshot(
                [
                    "SELECT table_mapped_book.id,",
                    "       table_mapped_book.title",
                    "  FROM (",
                    "        SELECT table_mapped_book.title AS title,",
                    "               table_mapped_book.id AS id",
                    "          FROM table_mapped_book AS table_mapped_book",
                    "         ORDER BY table_mapped_book.id ASC",
                    "         LIMIT %(param_1)s",
                    "        OFFSET %(param_2)s",
                    "       ) AS table_mapped_book",
                    " ORDER BY table_mapped_book.id ASC",
                ]
            ),
            id="root-subquery",
        ),
        pytest.param(
            "{ books { author { booksAggregate { count } } } }",
            snapshot(
                [
                    "SELECT table_mapped_book.id,",
                    "       table_mapped_author_1.id AS id_1,",
                    "       table_mapped_author_1.id AS table_mapped_book__author__id,",
                    "       anon_1.count_1",
                    "  FROM table_mapped_book AS table_mapped_book",
                    "  LEFT OUTER JOIN table_mapped_author AS table_mapped_author_1",
                    "    ON table_mapped_author_1.id = table_mapped_book.author_id",
                    "  JOIN LATERAL (",
                    "        SELECT count(*) AS count_1",
                    "          FROM table_mapped_book AS table_mapped_book_1",
                    "         WHERE table_mapped_author_1.id = table_mapped_book_1.author_id",
                    "       ) AS anon_1",
                    "    ON TRUE",
                    " ORDER BY table_mapped_book.id ASC,",
                    "          table_mapped_author_1.id ASC",
                ]
            ),
            id="relation-computed",
        ),
    ],
)
@pytest.mark.inline_snapshot
def test_table_mapped_model_sql(query: str, expected: list[str], captured_statements: list[Select[Any]]) -> None:
    """Test that a model mapped without ``__tablename__`` names its aliases after its mapped table."""
    result = schema.execute_sync(query, context_value=MockContext("postgresql"))

    assert not result.errors
    assert format_sql(str(captured_statements[0].compile(dialect=SQLA_DIALECTS["postgresql"]))).splitlines() == expected
