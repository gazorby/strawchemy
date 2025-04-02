from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias

from sqlalchemy.orm import ColumnProperty, RelationshipProperty, joinedload, selectinload, undefer
from sqlalchemy.orm.strategy_options import _AbstractLoad
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


ColumnLoadingMode: TypeAlias = Literal["undefer", "add"]
RelationshipLoadSpec: TypeAlias = "tuple[InstrumentedAttribute[Any], Sequence[_LoadType]]"

_LoadType: TypeAlias = "InstrumentedAttribute[Any] | RelationshipLoadSpec"


@dataclass
class QueryHook(Generic[DeclarativeT]):
    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    load: Sequence[_LoadType] = field(default_factory=list)

    _columns: list[InstrumentedAttribute[Any]] = field(init=False, default_factory=list)
    _relationships: list[tuple[InstrumentedAttribute[Any], Sequence[_LoadType]]] = field(
        init=False, default_factory=list
    )

    def __post_init__(self) -> None:
        for attribute in self.load:
            is_mapping = isinstance(attribute, tuple)
            if not is_mapping:
                if isinstance(attribute.property, ColumnProperty):
                    self._columns.append(attribute)
                if isinstance(attribute.property, RelationshipProperty):
                    self._relationships.append((attribute, []))
                continue
            self._relationships.append(attribute)
        self._check_relationship_load_spec(self._relationships)

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

    def _load_relationships(
        self, load_spec: RelationshipLoadSpec, parent_alias: AliasedClass[Any] | None = None
    ) -> _AbstractLoad:
        relationship, attributes = load_spec
        alias_relationship = getattr(parent_alias, relationship.key) if parent_alias else relationship
        load = joinedload(alias_relationship) if parent_alias is None else selectinload(alias_relationship)
        columns = []
        children_loads: list[_AbstractLoad] = []
        for attribute in attributes:
            if isinstance(attribute, tuple):
                children_loads.append(self._load_relationships(attribute))
            else:
                columns.append(attribute)
        if columns:
            load = load.load_only(*columns)
        if children_loads:
            load = load.options(*children_loads)
        return load

    @property
    def info(self) -> Info[Any, Any]:
        if info := self.info_var.get():
            return info
        msg = "info context is not available"
        raise QueryHookError(msg)

    def load_relationships(self, alias: AliasedClass[Any]) -> list[_AbstractLoad]:
        return [self._load_relationships(load_spec, alias) for load_spec in self._relationships]

    def load_columns(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[Any], mode: ColumnLoadingMode
    ) -> tuple[Select[tuple[DeclarativeT]], list[_AbstractLoad]]:
        load_options: list[_AbstractLoad] = []
        for column in self._columns:
            alias_attribute = getattr(alias, column.key)
            if mode == "undefer":
                load_options.append(undefer(alias_attribute))
            else:
                statement = statement.add_columns(alias_attribute)
        return statement, load_options

    def apply_hook(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        return statement
