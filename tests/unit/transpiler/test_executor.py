"""DB-free tests for QueryExecutor plan-driven statement assembly."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Result, Select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import MultipleResultsFound

from strawchemy.exceptions import QueryResultError
from strawchemy.transpiler._core.level import Level, PlanContext
from strawchemy.transpiler._core.request import QueryRequest
from strawchemy.transpiler._executor import NodeResult, SyncQueryExecutor
from strawchemy.transpiler._passes import DEFAULT_PIPELINES
from tests.unit.models import Fruit

if TYPE_CHECKING:
    from strawchemy.transpiler._core.plan import QueryPlan


def _plan(limit: int | None = None) -> QueryPlan:
    """Plans a query over the Fruit model for executor tests."""
    context = PlanContext.create(Fruit, postgresql.dialect(), pipelines=DEFAULT_PIPELINES)
    request = QueryRequest(Fruit, None, None, (), (), limit, None, False)
    return context.pipelines.root.plan(Level.root(request, context))


def _result(*models: object) -> MagicMock:
    """Builds a mock ``Result`` yielding one computed-value-free row per model.

    Returns:
        A ``MagicMock`` standing in for a SQLAlchemy ``Result``.
    """
    rows: list[MagicMock] = []
    for model in models:
        row = MagicMock()
        row.__getitem__.return_value = model
        row._mapping = {}  # noqa: SLF001  # Row exposes computed values only via _mapping.
        rows.append(row)
    result = MagicMock(spec=Result)
    result.all.return_value = rows
    return result


def test_executor_emits_plan_in_statement() -> None:
    """statement() emits the held plan into a Select."""
    executor = SyncQueryExecutor(plan=_plan(), id_field_definitions=[])
    assert isinstance(executor.statement(), Select)


@pytest.mark.parametrize("limit", [None, 2], ids=["plain", "paginated"])
def test_executor_add_where_reads_the_root_alias(limit: int | None) -> None:
    """add_where predicates on the unaliased model are moved onto the plan's root alias, adding no FROM."""
    executor = SyncQueryExecutor(plan=_plan(limit), id_field_definitions=[])
    planned_froms = len(executor.statement().get_final_froms())
    executor.add_where(Fruit.id == uuid4())
    statement = executor.statement()
    assert "WHERE" in str(statement)
    assert len(statement.get_final_froms()) == planned_froms


def test_executor_rejects_several_roots_when_fetching_one() -> None:
    """get_one_or_none raises when the returned rows fold onto more than one root."""
    session = MagicMock()
    session.execute.return_value = _result(Fruit(), Fruit())
    executor = SyncQueryExecutor(plan=_plan(), id_field_definitions=[])
    with pytest.raises(MultipleResultsFound):
        executor.get_one_or_none(session)


def test_executor_folds_rows_onto_their_root() -> None:
    """Rows repeating the same root collapse onto a single node."""
    session = MagicMock()
    fruit = Fruit()
    session.execute.return_value = _result(fruit, fruit)
    executor = SyncQueryExecutor(plan=_plan(), id_field_definitions=[])
    assert executor.list(session).nodes == [fruit]


def test_node_result_rejects_relation_not_selected() -> None:
    """value() raises for a relation node the query did not select, rather than reading the model attribute."""
    relation = SimpleNamespace(
        value=SimpleNamespace(is_computed=False, is_relation=True, name="color"),
        metadata=SimpleNamespace(data=SimpleNamespace(is_transform=False)),
    )
    with pytest.raises(QueryResultError, match="'color'"):
        NodeResult(model=Fruit(), computed_values={}).value(cast("Any", relation))
