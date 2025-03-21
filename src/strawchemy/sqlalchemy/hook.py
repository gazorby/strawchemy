from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, override

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


@dataclass
class QueryHookResult(Generic[DeclarativeT]):
    statement: Select[tuple[DeclarativeT]]
    load_options: list[_AbstractLoad] = field(default_factory=list)


@dataclass(frozen=True, eq=True)
class QueryHook(Generic[DeclarativeT]):
    load_columns: Sequence[InstrumentedAttribute[Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if any(isinstance(element.property, RelationshipProperty) for element in self.load_columns):
            msg = "Relationships are not supported `load_columns`"
            raise QueryHookError(msg)

    def _apply_hook(
        self,
        statement: Select[tuple[DeclarativeT]],
        alias: AliasedClass[Any],
        mode: Literal["load_options", "statement"],
    ) -> QueryHookResult[DeclarativeT]:
        load_options: list[_AbstractLoad] = []
        for column in self.load_columns:
            alias_attribute = getattr(alias, column.key)
            if mode == "load_options":
                load_options.append(undefer(alias_attribute))
            else:
                statement = statement.add_columns(alias_attribute)
        return QueryHookResult(statement=statement, load_options=load_options)

    def __call__(
        self,
        statement: Select[tuple[DeclarativeT]],
        alias: AliasedClass[DeclarativeT],
        mode: Literal["load_options", "statement"],
    ) -> QueryHookResult[DeclarativeT]:
        return self._apply_hook(statement, alias, mode)

    @override
    def __hash__(self) -> int:
        return hash(tuple(self.load_columns))
