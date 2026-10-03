"""Helpers planning a query with the pass pipelines and reading its SQL."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

import pytest

from strawchemy.transpiler import AsyncQueryExecutor, SyncQueryExecutor
from tests.duplicate_reads import assert_no_duplicate_reads
from tests.unit.conftest import empty_query_result
from tests.unit.schemas.optimizations import schema
from tests.unit.utils import SQLA_DIALECTS, DialectContext
from tests.utils import format_sql

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy import Select

    from strawchemy.transpiler._core.pipeline import Pipelines
    from strawchemy.typing import SupportedDialect

__all__ = ("coalesced", "outer_order_by", "outer_projection", "plan_sql")


def coalesced(column: str, dialect_name: str) -> str:
    """Returns how ``column``, a count read through an outer CTE join, is selected on ``dialect_name``."""
    if dialect_name == "postgresql":
        return column
    placeholder = "?" if dialect_name == "sqlite" else "%s"
    return f"coalesce({column}, {placeholder}) AS coalesce_1"


def outer_order_by(lines: list[str]) -> list[str]:
    """Returns the terms of the outermost ORDER BY of ``lines``, as ``plan_sql`` formats them."""
    start = next(index for index, line in enumerate(lines) if line.startswith(" ORDER BY"))
    return [line.strip(" ,").removeprefix("ORDER BY ") for line in lines[start:]]


def outer_projection(lines: list[str]) -> list[str]:
    """Returns the columns of the outermost SELECT list of ``lines``, as ``plan_sql`` formats them.

    The outer SELECT is the only one at the statement's own indentation; a CTE's ends the line closing its body.
    """
    columns: list[str] = []
    for line in lines:
        if not columns:
            if (match := re.match(r"(?:\s*\) )?SELECT (.*)", line)) is not None:
                columns.append(match.group(1).strip().rstrip(","))
        elif line.startswith("  FROM"):
            break
        else:
            columns.append(line.strip().rstrip(","))
    return columns


def plan_sql(
    query: str, dialect_name: str, pipelines: Pipelines | None = None, *, literal_binds: bool = False
) -> list[str]:
    """Plans ``query`` with ``pipelines``, by default the pass pipelines, and returns its statement as SQL lines.

    Raises:
        AssertionError: If the statement reads the same rows twice.
    """
    captured: list[Select[Any]] = []

    def _execute(self: SyncQueryExecutor[Any], session: object) -> MagicMock:  # noqa: ARG001
        captured.append(cast("Select[Any]", self.statement()))
        return empty_query_result()

    async def _async_execute(self: AsyncQueryExecutor[Any], session: object) -> MagicMock:  # noqa: ARG001
        captured.append(cast("Select[Any]", self.statement()))
        return empty_query_result()

    with pytest.MonkeyPatch.context() as patch:
        if pipelines is not None:
            patch.setattr("strawchemy.transpiler._transpiler.DEFAULT_PIPELINES", pipelines)
        patch.setattr(SyncQueryExecutor[Any], "execute", _execute)
        patch.setattr(AsyncQueryExecutor[Any], "execute", _async_execute)
        context = DialectContext(cast("SupportedDialect", dialect_name))
        result = schema.execute_sync(query, context_value=context)
    assert not result.errors, result.errors
    assert len(captured) == 1
    dialect = SQLA_DIALECTS[dialect_name]
    assert_no_duplicate_reads(captured[0], dialect)
    compiled = captured[0].compile(dialect=dialect, compile_kwargs={"literal_binds": literal_binds})
    return format_sql(str(compiled)).splitlines()
