"""``QueryHook``, the base class for loading extra columns and relations or editing the generated SELECT."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias

from sqlalchemy.orm import (
    ColumnProperty,
    Composite,
    QueryableAttribute,
    RelationshipProperty,
    class_mapper,
    joinedload,
    selectinload,
    undefer,
)

from strawchemy.exceptions import QueryHookError
from strawchemy.repository.typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapper
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass
    from strawberry import Info


ColumnLoadingMode: TypeAlias = Literal["undefer", "add"]
RelationshipLoadSpec: TypeAlias = "tuple[InstrumentedAttribute[Any], Sequence[LoadType]]"

LoadType: TypeAlias = "InstrumentedAttribute[Any] | RelationshipLoadSpec"


class _UnsetLoad(list["LoadType"]):
    """Default of ``QueryHook.load``, telling an omitted argument apart from an explicit one."""


def _loaded_property(attribute: object) -> ColumnProperty[Any] | RelationshipProperty[Any] | Composite[Any] | None:
    """Returns the property ``attribute`` loads, through synonyms and hybrids; ``None`` if it loads none."""
    if not isinstance(attribute, QueryableAttribute):
        return None
    try:
        prop = attribute.property
    except AttributeError:
        return None
    return prop if isinstance(prop, (ColumnProperty, RelationshipProperty, Composite)) else None


@dataclass
class QueryHook(Generic[DeclarativeT]):
    """Loads extra columns and relations, or edits the SELECT, for the field it is attached to.

    Override ``apply_hook`` to edit the statement; read the current request from ``info``.
    """

    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    """Strawberry ``Info`` of the current request."""
    load: Sequence[LoadType] = field(default_factory=_UnsetLoad)
    """Columns and relations to load, a relation with its own list.

    Example: ``[User.name, (User.addresses, [Address.street])]``
    """

    _columns: list[InstrumentedAttribute[Any]] = field(init=False, default_factory=list)
    _relationships: list[tuple[InstrumentedAttribute[Any], Sequence[LoadType]]] = field(
        init=False, default_factory=list
    )
    _checked_mappers: set[Mapper[Any]] = field(init=False, default_factory=set, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Splits ``load`` into the columns and the relationships the hook loads."""
        if isinstance(self.load, _UnsetLoad):
            # The inherited ``__init__`` shadows a ``load`` set as a plain class attribute on a subclass.
            self.load = list(getattr(type(self), "load", ()))
        for attribute in self._normalize_load_spec(self.load):
            if isinstance(attribute, tuple):
                self._relationships.append(attribute)
            else:
                self._columns.append(attribute)

    def _normalize_load_spec(
        self, load_spec: Sequence[LoadType], parent: RelationshipProperty[Any] | None = None
    ) -> list[LoadType]:
        """Returns the columns and relationships ``load_spec`` loads under ``parent``, each relationship with its list.

        Raises:
            QueryHookError: If a key is not a relationship, or an attribute is not a column or relationship of
                ``parent``'s model.
        """
        normalized: list[LoadType] = []
        for item in load_spec:
            attribute, attributes = item if isinstance(item, tuple) else (item, None)
            prop = _loaded_property(attribute)
            if attributes is not None and not isinstance(prop, RelationshipProperty):
                msg = f"Keys of mappings passed in `load` param must be relationship attributes: {attribute}"
                raise QueryHookError(msg)
            if prop is None:
                msg = f"Attributes passed in `load` param must be column or relationship attributes: {attribute}"
                raise QueryHookError(msg)
            # ``isa`` rejects a subclass attribute under a base class relationship, which loaders do too.
            if parent is not None and not parent.mapper.isa(prop.parent):
                msg = (
                    f"Attributes nested under {parent} in `load` param must belong to "
                    f"{parent.mapper.class_.__name__}: {attribute}"
                )
                raise QueryHookError(msg)
            if isinstance(prop, RelationshipProperty):
                normalized.append((prop.class_attribute, self._normalize_load_spec(attributes or [], prop)))
            elif isinstance(prop, Composite):
                normalized.extend(self._normalize_load_spec([member.class_attribute for member in prop.props], parent))
            else:
                normalized.append(prop.class_attribute)
        return normalized

    def check_model(self, model: type[DeclarativeBase]) -> None:
        """Checks that the top-level attributes of ``load`` can be loaded from ``model``.

        Raises:
            QueryHookError: If an attribute belongs neither to ``model`` nor to a model it inherits from.
        """
        mapper = class_mapper(model)
        if mapper in self._checked_mappers:
            return
        for item in self.load:
            attribute = item[0] if isinstance(item, tuple) else item
            prop = _loaded_property(attribute)
            if prop is not None and not mapper.isa(prop.parent):
                msg = f"Attributes passed in `load` param must belong to {model.__name__}: {attribute}"
                raise QueryHookError(msg)
        self._checked_mappers.add(mapper)

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
                attribute = getattr(alias, column.key).__clause_element__()
                if not any(attribute.compare(selected) for selected in statement.selected_columns):
                    statement = statement.add_columns(attribute)
        return statement, load_options

    def apply_hook(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[DeclarativeT]
    ) -> Select[tuple[DeclarativeT]]:
        """Returns ``statement`` edited, for instance with a filter or a join; unchanged by default.

        ``alias`` is the alias of the model the hook's field belongs to.
        """
        return statement
