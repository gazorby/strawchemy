"""``QueryHook``, the base class for loading extra columns and relations or editing the generated SELECT."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias

from sqlalchemy.orm import ColumnProperty, RelationshipProperty, joinedload, selectinload, undefer

from strawchemy.exceptions import QueryHookError
from strawchemy.repository.typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from strawberry import Info


ColumnLoadingMode: TypeAlias = Literal["undefer", "add"]
RelationshipLoadSpec: TypeAlias = "tuple[InstrumentedAttribute[Any], Sequence[LoadType]]"

LoadType: TypeAlias = "InstrumentedAttribute[Any] | RelationshipLoadSpec"


@dataclass
class QueryHook(Generic[DeclarativeT]):
    """Loads extra columns and relations, or edits the SELECT, for the field it is attached to.

    Override ``apply_hook`` to edit the statement; read the current request from ``info``.
    """

    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    """Strawberry ``Info`` of the current request."""
    load: Sequence[LoadType] = field(default_factory=list)
    """Columns and relations to load, a relation with its own list.

    Example: ``[User.name, (User.addresses, [Address.street])]``
    """

    _columns: list[InstrumentedAttribute[Any]] = field(init=False, default_factory=list)
    _relationships: list[tuple[InstrumentedAttribute[Any], Sequence[LoadType]]] = field(
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
        self, load_spec: list[tuple[InstrumentedAttribute[Any], Sequence[LoadType]]]
    ) -> None:
        """Checks that every key of ``load_spec``, nested ones included, is a relationship.

        Raises:
            QueryHookError: If a key is not a relationship attribute.
        """
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
        """Builds the loader option of one relation and its listed columns and sub-relations.

        Uses ``selectinload`` from ``parent_alias`` when given, ``joinedload`` otherwise.
        """
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
        """Strawberry ``Info`` of the current request.

        Raises:
            QueryHookError: If no request is being resolved.
        """
        if info := self.info_var.get():
            return info
        msg = "info context is not available"
        raise QueryHookError(msg)

    def load_relationships(self, alias: AliasedClass[Any]) -> list[_AbstractLoad]:
        """Returns the loader options of the relations in ``load``, loaded from ``alias``."""
        return [self._load_relationships(load_spec, alias) for load_spec in self._relationships]

    def column_load_options(self, alias: AliasedClass[Any]) -> list[_AbstractLoad]:
        """Returns ``undefer`` options for the columns in ``load``, read from ``alias``."""
        return [undefer(getattr(alias, column.key)) for column in self._columns]

    def load_columns(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[Any], mode: ColumnLoadingMode
    ) -> tuple[Select[tuple[DeclarativeT]], list[_AbstractLoad]]:
        """Loads the columns in ``load``, as ``undefer`` options or, in ``"add"`` mode, as selected columns."""
        load_options: list[_AbstractLoad] = []
        if mode == "undefer":
            load_options = self.column_load_options(alias)
        else:
            for column in self._columns:
                statement = statement.add_columns(getattr(alias, column.key))
        return statement, load_options

    def apply_hook(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        """Returns ``statement`` edited, for instance with a filter or a join; unchanged by default.

        ``alias`` is the alias of the model the hook's field belongs to.
        """
        return statement
