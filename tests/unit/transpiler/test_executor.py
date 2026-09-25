"""DB-free tests for QueryExecutor plan-driven statement assembly."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Result, Select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import aliased, load_only

from strawchemy.exceptions import QueryResultError
from strawchemy.transpiler._executor import NodeResult, SyncQueryExecutor
from strawchemy.transpiler._plan import QueryPlan
from tests.unit.models import Fruit

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass


def _plan() -> QueryPlan:
    """Builds a minimal QueryPlan over the Fruit model for executor tests."""
    fruit: AliasedClass[Fruit] = cast("AliasedClass[Fruit]", aliased(Fruit))
    return QueryPlan(root=fruit, filter_semijoin=None, load_options=(load_only(fruit.name),))


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


def test_executor_add_where_appends_predicate() -> None:
    """add_where predicates are applied on top of the emitted statement."""
    executor = SyncQueryExecutor(plan=_plan(), id_field_definitions=[])
    executor.add_where(executor.plan.root.name == "x")
    compiled = str(executor.statement())
    assert "WHERE" in compiled


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
