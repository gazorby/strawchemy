from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias
from unittest.mock import MagicMock

import pytest

from sqlalchemy import Result
from strawchemy.sqlalchemy import _executor as executor
from strawchemy.sqlalchemy._scope import NodeInspect

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from strawchemy.dto import ModelT
    from strawchemy.graphql.dto import QueryNode
    from strawchemy.sqlalchemy.typing import AnySession, DeclarativeT


SyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], MagicMock]"
AsyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], Awaitable[MagicMock]]"


def make_execute(computed_values: dict[str, Any], model_instance: Any) -> SyncExecuteCallable[DeclarativeT]:
    def _execute(self: executor.QueryExecutor[DeclarativeT], session: AnySession) -> MagicMock:  # noqa: ARG001
        rows = []
        if computed_values:
            row_tuple = (model_instance, *computed_values.values())
            row_fields = (model_instance, *computed_values.keys())
        else:
            row_tuple, row_fields = (model_instance,), (model_instance,)
        rows = [MagicMock(name="RowMock", __iter__=MagicMock(return_value=iter(row_tuple)), _fields=row_fields)]
        self.statement()
        result = MagicMock(
            spec=Result,
            name="ResultMock",
            all=MagicMock(return_value=iter(rows)),
            one_or_none=MagicMock(return_value=rows[0]),
        )

        result.unique.return_value = result
        return result

    return _execute


def make_async_execute(computed_values: dict[str, Any], model_instance: Any) -> AsyncExecuteCallable[DeclarativeT]:
    execute_func = make_execute(computed_values, model_instance)

    async def _execute(self: executor.QueryExecutor[DeclarativeT], session: AnySession) -> MagicMock:
        return execute_func(self, session)

    return _execute


@pytest.fixture(name="model_instance")
def fx_model_instance() -> dict[str, Any]:
    return MagicMock(name="InstanceMock")


@pytest.fixture(name="computed_values")
def fx_computed_values() -> dict[str, Any]:
    return {}


@pytest.fixture(name="patch_query", autouse=True)
def fx_patch_query(monkeypatch: pytest.MonkeyPatch, computed_values: dict[str, Any], model_instance: Any) -> None:
    def node_result_value(self: executor.NodeResult[ModelT], key: QueryNode[Any, Any]) -> Any:
        key_str = self.node_key(key)
        if key.value.is_computed:
            for name, value in self.computed_values.items():
                if name in key_str:
                    return value
        if any(func in key_str for func in NodeInspect.sqla_functions_map):
            return 0
        return getattr(self.model, key.value.model_field_name)

    def query_result_value(self: executor.QueryResult[ModelT], key: QueryNode[Any, Any]) -> Any:
        key_str = self.node_key(key)
        for name, value in computed_values.items():
            if name in key_str:
                return value
        if any(func in key_str for func in NodeInspect.sqla_functions_map):
            return 0
        return None

    monkeypatch.setattr(
        executor.AsyncQueryExecutor[Any], "execute", make_async_execute(computed_values, model_instance)
    )
    monkeypatch.setattr(executor.SyncQueryExecutor[Any], "execute", make_execute(computed_values, model_instance))
    monkeypatch.setattr(executor.NodeResult, "value", node_result_value)
    monkeypatch.setattr(executor.QueryResult, "value", query_result_value)


@pytest.fixture
def context() -> MockContext:
    return MockContext()


@dataclass
class MockContext:
    session: MagicMock = dataclasses.field(default_factory=lambda: MagicMock(name="SessionMock"))
