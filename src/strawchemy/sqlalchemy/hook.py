from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias

from sqlalchemy.orm import ColumnProperty, RelationshipProperty
from sqlalchemy.orm.util import AliasedClass

from .exceptions import QueryHookError
from .typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.orm.util import AliasedClass
    from strawberry import Info


RelationshipLoadSpec: TypeAlias = "tuple[InstrumentedAttribute[Any], Sequence[_LoadType]]"
_LoadType: TypeAlias = "InstrumentedAttribute[Any] | RelationshipLoadSpec"


@dataclass
class QueryHook(Generic[DeclarativeT]):
    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    load: Sequence[_LoadType] = field(default_factory=list)
    load_columns: list[InstrumentedAttribute[Any]] = field(init=False, default_factory=list)
    load_relationships: list[tuple[InstrumentedAttribute[Any], Sequence[_LoadType]]] = field(
        init=False, default_factory=list
    )

    def __post_init__(self) -> None:
        for attribute in self.load:
            is_mapping = isinstance(attribute, tuple)
            if not is_mapping:
                if isinstance(attribute.property, ColumnProperty):
                    self.load_columns.append(attribute)
                if isinstance(attribute.property, RelationshipProperty):
                    self.load_relationships.append((attribute, []))
                continue
            self.load_relationships.append(attribute)
        self._check_relationship_load_spec(self.load_relationships)

    def _check_relationship_load_spec(
        self, load_spec: list[tuple[InstrumentedAttribute[Any], Sequence[_LoadType]]]
    ) -> None:
        for key, attributes in load_spec:
            for attribute in attributes:
                if isinstance(attribute, list):
                    self._check_relationship_load_spec(attribute)
                if not isinstance(key.property, RelationshipProperty):
                    msg = f"Keys of mappings passed in `load` param must be relationship attributes: {key}"
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
