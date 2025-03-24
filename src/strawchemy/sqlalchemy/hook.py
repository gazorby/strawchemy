from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic

from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.orm.util import AliasedClass

from .exceptions import QueryHookError
from .typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.orm.util import AliasedClass
    from strawberry import Info


@dataclass
class QueryHook(Generic[DeclarativeT]):
    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    load_columns: Sequence[InstrumentedAttribute[Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if any(isinstance(element.property, RelationshipProperty) for element in self.load_columns):
            msg = "Relationships are not supported `load_columns`"
            raise QueryHookError(msg)

    @property
    def info(self) -> Info[Any, Any]:
        if info := self.info_var.get():
            return info
        msg = "info context is not available"
        raise QueryHookError(msg)

    def apply_hook(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        return statement
