"""DB-free tests for QueryExecutor plan-driven statement assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import Select
from sqlalchemy.orm import aliased, load_only

from strawchemy.transpiler._executor import SyncQueryExecutor
from strawchemy.transpiler._plan import QueryPlan
from tests.unit.models import Fruit

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass


def _plan() -> QueryPlan:
    """Builds a minimal QueryPlan over the Fruit model for executor tests."""
    fruit: AliasedClass[Fruit] = cast("AliasedClass[Fruit]", aliased(Fruit))
    return QueryPlan(root=fruit, filter_semijoin=None, load_options=(load_only(fruit.name),))


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
