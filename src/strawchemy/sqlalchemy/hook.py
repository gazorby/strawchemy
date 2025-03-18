from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, override

from sqlalchemy.orm import RelationshipProperty, joinedload, selectinload, undefer
from sqlalchemy.orm.strategy_options import _AbstractLoad
from sqlalchemy.orm.util import AliasedClass

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
    always_load: Sequence[InstrumentedAttribute[Any]] = field(default_factory=tuple)

    def _add_columns(
        self, statement: Select[tuple[DeclarativeT]], columns: list[InstrumentedAttribute[Any]]
    ) -> QueryHookResult[DeclarativeT]:
        options: list[_AbstractLoad] = []
        for column in columns:
            if isinstance(column.property, RelationshipProperty):
                load = (
                    selectinload(column)
                    if column.property.uselist
                    else joinedload(column, innerjoin=column.property.innerjoin)
                )
            else:
                load = undefer(column)
            options.append(load)
        return QueryHookResult(statement=statement, load_options=options)

    def __call__(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> QueryHookResult[DeclarativeT]:
        if self.always_load:
            return self._add_columns(statement, [getattr(alias, column.key) for column in self.always_load])
        return QueryHookResult(statement=statement)

    @override
    def __hash__(self) -> int:
        return hash(tuple(self.always_load))
