from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, override

from sqlalchemy.orm import RelationshipProperty, undefer
from sqlalchemy.orm.util import AliasedClass

from .exceptions import QueryHookError
from .typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from strawberry import Info


class QueryHookProtocol(Protocol, Generic[DeclarativeT]):
    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)

    @property
    def info(self) -> Info[Any, Any]:
        if info := self.info_var.get():
            return info
        msg = "info context is not available"
        raise QueryHookError(msg)

    def apply_hook_on_statement(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        return statement

    def apply_hook_on_load_options(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> list[_AbstractLoad]:
        return []


@dataclass(frozen=True, eq=True)
class LoadColumnsHook(QueryHookProtocol[DeclarativeT]):
    columns: Sequence[InstrumentedAttribute[Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if any(isinstance(element.property, RelationshipProperty) for element in self.columns):
            msg = "Relationships are not supported `load_columns`"
            raise QueryHookError(msg)

    @override
    def apply_hook_on_load_options(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> list[_AbstractLoad]:
        load_options: list[_AbstractLoad] = []
        for column in self.columns:
            alias_attribute = getattr(alias, column.key)
            load_options.append(undefer(alias_attribute))
        return load_options

    @override
    def apply_hook_on_statement(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        for column in self.columns:
            alias_attribute = getattr(alias, column.key)
            statement = statement.add_columns(alias_attribute)
        return statement

    @override
    def __hash__(self) -> int:
        return hash(tuple(self.columns))


@dataclass
class FilterOrderHook(QueryHookProtocol[DeclarativeT]):
    def statement(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        return statement

    @override
    def apply_hook_on_statement(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        return self.statement(statement, alias)
