from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, Text, and_, create_engine, insert, select

from strawchemy.schema.filters import TextComparison

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Connection

_TABLE = Table("like_filter", MetaData(), Column("id", Integer, primary_key=True), Column("value", Text))
_RANDOM = random.Random(361)  # noqa: S311  # seeded test data, not cryptography
# Upper and lower ASCII letters, which SQLite's own LIKE folds, and a newline, which LIKE wildcards match.
_VALUES = sorted({"".join(_RANDOM.choice("abAB\n") for _ in range(_RANDOM.randint(0, 8))) for _ in range(60)})
_PATTERNS = sorted({"".join(_RANDOM.choice("ab%_") for _ in range(_RANDOM.randint(0, 6))) for _ in range(3000)})


@pytest.fixture(scope="module")
def connection() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        _TABLE.create(connection)
        connection.execute(insert(_TABLE), [{"value": value} for value in _VALUES])
        yield connection
    engine.dispose()


def test_sqlite_ilike_matches_native_like(connection: Connection) -> None:
    """Test that ilike and nilike on SQLite select the same ASCII rows as SQLite's own case-insensitive LIKE."""
    mismatches: list[str] = []
    for pattern in _PATTERNS:
        native = set(connection.scalars(select(_TABLE.c.id).where(_TABLE.c.value.like(pattern))))
        for operator, expected in (("ilike", native), ("nilike", set(range(1, len(_VALUES) + 1)) - native)):
            comparison = TextComparison(**{operator: pattern})
            where = and_(*comparison.to_expressions(connection.dialect, _TABLE.c.value))
            if set(connection.scalars(select(_TABLE.c.id).where(where))) != expected:
                mismatches.append(f"{operator}: {pattern!r}")

    assert not mismatches
