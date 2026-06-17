from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Result

from strawchemy.transpiler import _executor as executor
from strawchemy.transpiler._scope import AggregationFunctionInfo

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from strawchemy.dto import ModelT
    from strawchemy.dto.strawberry import QueryNode
    from strawchemy.repository.typing import AnySession, DeclarativeT
    from strawchemy.typing import SupportedDialect


SyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], MagicMock]"
AsyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], Awaitable[MagicMock]]"


def make_execute(computed_values: dict[str, Any], model_instance: Any) -> SyncExecuteCallable[DeclarativeT]:
    def _execute(self: executor.QueryExecutor[DeclarativeT], session: AnySession) -> MagicMock:  # noqa: ARG001
        # The executor reads computed values by Label identity from ``row._mapping``. Match each
        # column-map label to a value by its node name so name-keyed ``computed_values`` still apply.
        mapping = {model_instance: model_instance}
        for node, label in self.column_map.items():
            mapping[label] = computed_values.get(node.value.name)
        rows = [MagicMock(name="RowMock", __getitem__=lambda _self, _index: model_instance, _mapping=mapping)]
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
    def node_result_value(self: executor.NodeResult[ModelT], key: QueryNode) -> Any:
        key_name = key.value.name
        if key.value.is_computed:
            for name, value in computed_values.items():
                if name in key_name:
                    return value
        if any(func in key_name for func in AggregationFunctionInfo.functions_map):
            return 0
        return getattr(self.model, key.value.model_field_name)

    def query_result_value(self: executor.QueryResult[ModelT], key: QueryNode) -> Any:  # noqa: ARG001
        key_name = key.value.name
        for name, value in computed_values.items():
            if name in key_name:
                return value
        if any(func in key_name for func in AggregationFunctionInfo.functions_map):
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
    return MockContext("postgresql")


@dataclass
class MockContext:
    dialect: SupportedDialect
    session: MagicMock = field(init=False)

    def __post_init__(self) -> None:
        dialect = MagicMock(name="DialectMock")
        dialect.name = "postgresql"
        engine = MagicMock(name="EngineMock", dialect=dialect)
        self.session = MagicMock(name="SessionMock", get_bind=MagicMock(return_value=engine))
