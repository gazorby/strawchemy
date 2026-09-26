from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias
from unittest.mock import MagicMock, NonCallableMock

import pytest
from sqlalchemy import Result
from strawberry.utils.str_converters import to_camel_case

from strawchemy.transpiler import _executor as executor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from strawchemy.dto import ModelT
    from strawchemy.dto.strawberry import QueryNode
    from strawchemy.repository.typing import AnySession, DeclarativeT
    from strawchemy.typing import QueryNodeType, SupportedDialect


SyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], MagicMock]"
AsyncExecuteCallable: TypeAlias = "Callable[[executor.QueryExecutor[DeclarativeT], AnySession], Awaitable[MagicMock]]"


def _names(node: QueryNodeType) -> frozenset[str]:
    if node.is_root:
        return frozenset(node.metadata.data.response_keys)
    return frozenset((node.value.name, to_camel_case(node.value.name), *node.metadata.data.response_keys))


def _path_names(node: QueryNodeType) -> list[frozenset[str]]:
    return [_names(path_node) for path_node in node.path_from_root()]


def _key_matches(key: str, path_names: list[frozenset[str]]) -> bool:
    segments = key.split(".")
    return len(segments) <= len(path_names) and all(
        segment in names for segment, names in zip(reversed(segments), reversed(path_names), strict=False)
    )


def _computed_value(node: QueryNodeType, computed_values: dict[str, Any]) -> object:
    path_names = _path_names(node)
    if matching := [key for key in computed_values if _key_matches(key, path_names)]:
        return computed_values[max(matching, key=lambda key: key.count("."))]
    function = node.value.function()
    return 0 if function is not None and function.function == "count" else None


def make_execute(computed_values: dict[str, Any], model_instance: Any) -> SyncExecuteCallable[DeclarativeT]:
    def _execute(self: executor.QueryExecutor[DeclarativeT], session: AnySession) -> MagicMock:  # noqa: ARG001
        # The executor reads computed values by Label identity from ``row._mapping``.
        mapping = {model_instance: model_instance}
        for columns in self.identity_columns.values():
            mapping.update(dict.fromkeys(columns))
        for node, label in self.column_map.items():
            mapping[label] = _computed_value(node, computed_values)
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
    """Values returned for aggregation fields, keyed by a dotted path of field names, aliases or Python names.

    A key matches the trailing fields of a path from the queried root field, such as ``count``, ``max.sweetness`` or
    ``colors.fruitsAggregate.count``; the longest matching key wins, and on ties the first one. Unmatched ``count``
    fields return ``0``, other aggregation fields ``None``.
    """
    return {}


@pytest.fixture(name="patch_query", autouse=True)
def fx_patch_query(monkeypatch: pytest.MonkeyPatch, computed_values: dict[str, Any], model_instance: Any) -> None:
    def node_result_value(self: executor.NodeResult[ModelT], key: QueryNode) -> Any:
        if key.value.is_computed:
            return _computed_value(key, computed_values)
        value = getattr(self.model, key.value.model_field_name)
        if key.value.is_relation and key.value.uselist:
            # A mock attribute stands for a single related object; wrap it so it reads as a collection.
            if isinstance(value, NonCallableMock):
                return [value]
            return list(value.values()) if isinstance(value, Mapping) else list(value)
        return value

    def query_result_value(self: executor.QueryResult[ModelT], key: QueryNode) -> Any:  # noqa: ARG001
        return _computed_value(key, computed_values)

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
