"""Defines the QueryHook interface and related utilities for customizing SQLAlchemy query generation.

This module provides the `QueryHook` base class, which allows developers to
intercept and modify SQLAlchemy `Select` statements at various stages of the
query building process. It also defines type aliases like `ColumnLoadingMode`
and `LoadType` used in conjunction with query hooks.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeAlias

from sqlalchemy.orm import ColumnProperty, RelationshipProperty, joinedload, selectinload, undefer
from sqlalchemy.orm.strategy_options import _AbstractLoad
from sqlalchemy.orm.util import AliasedClass

from strawchemy.sqlalchemy.exceptions import QueryHookError
from strawchemy.sqlalchemy.typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.orm.util import AliasedClass

    from sqlalchemy import Select
    from strawberry import Info


ColumnLoadingMode: TypeAlias = Literal["undefer", "add"]
RelationshipLoadSpec: TypeAlias = "tuple[InstrumentedAttribute[Any], Sequence[LoadType]]"

LoadType: TypeAlias = "InstrumentedAttribute[Any] | RelationshipLoadSpec"


@dataclass
class QueryHook(Generic[DeclarativeT]):
    """Base class for defining custom query modifications and data loading strategies.

    `QueryHook` instances are used to dynamically alter SQLAlchemy queries,
    primarily for specifying which columns and relationships should be eagerly
    loaded. This is often driven by the fields requested in a GraphQL query,
    made available via the `info` context variable.

    Attributes:
        load: A sequence defining which attributes (columns or relationships)
            to load. Relationships can be specified with nested load options.
            Example: `[User.name, (User.addresses, [Address.street])]`
        info_var: A class-level `ContextVar` to access the Strawberry `Info`
            object, providing context about the current GraphQL request.
    """

    info_var: ClassVar[ContextVar[Info[Any, Any] | None]] = ContextVar("info", default=None)
    load: Sequence[LoadType] = field(default_factory=list)

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
        """Recursively validates relationship load specifications.

        Ensures that the primary attribute in each part of a relationship
        load specification is indeed a SQLAlchemy `RelationshipProperty`.

        Args:
            load_spec: The relationship load specification to validate,
                typically `self._relationships` or a nested part of it.

        Raises:
            QueryHookError: If an attribute intended to specify a relationship
                is not a `RelationshipProperty`.
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
        """Constructs SQLAlchemy loader options for a relationship.

        Generates `joinedload` or `selectinload` options based on the
        `load_spec`. It supports loading specific columns of the related
        model (`load_only`) and applying further nested loader options.

        Args:
            load_spec: A tuple containing the relationship attribute
                and a sequence of attributes or nested relationships to load for it.
            parent_alias: The aliased class of the parent entity.
                If `None`, `joinedload` is used for the relationship.
                Otherwise, `selectinload` is used from the `parent_alias`.

        Returns:
            A SQLAlchemy `_AbstractLoad` object representing the loader strategy.
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
        """Provides access to the Strawberry GraphQL Info object.

        Retrieves the `Info` object from the `info_var` context variable.
        This object contains details about the current GraphQL request,
        which can be used to tailor the query.

        Returns:
            The Strawberry `Info` object.

        Raises:
            QueryHookError: If the `Info` object is not set in the context.
        """
        if info := self.info_var.get():
            return info
        msg = "info context is not available"
        raise QueryHookError(msg)

    def load_relationships(self, alias: AliasedClass[Any]) -> list[_AbstractLoad]:
        """Generates loader options for all configured relationships.

        Iterates over `self._relationships` and calls `_load_relationships`
        for each to create the appropriate SQLAlchemy loader options.

        Args:
            alias: The `AliasedClass` representing the entity to which these
                relationships are attached and should be loaded from.

        Returns:
            A list of SQLAlchemy `_AbstractLoad` objects.
        """
        return [self._load_relationships(load_spec, alias) for load_spec in self._relationships]

    def load_columns(
        self, statement: Select[tuple[DeclarativeT]], alias: AliasedClass[Any], mode: ColumnLoadingMode
    ) -> tuple[Select[tuple[DeclarativeT]], list[_AbstractLoad]]:
        """Applies column loading strategies to the SELECT statement.

        Modifies the given SQLAlchemy `Select` statement to ensure specified
        columns (from `self._columns`) are loaded.

        If `mode` is "undefer", it generates `undefer` options for the columns.
        If `mode` is "add", it adds the columns directly to the statement's
        selected entities.

        Args:
            statement: The SQLAlchemy `Select` statement to modify.
            alias: The `AliasedClass` of the entity from which columns are loaded.
            mode: The column loading mode, either "undefer" or "add".

        Returns:
            A tuple containing the potentially modified `Select` statement
            and a list of SQLAlchemy `_AbstractLoad` options (e.g., `undefer` options).
        """
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
        """Applies custom modifications to the SELECT statement.

        This method is intended to be overridden by subclasses to implement
        specific query alteration logic beyond column and relationship loading,
        such as adding filters, joins, or other clauses.

        By default, this base implementation returns the statement unchanged.

        Args:
            statement: The SQLAlchemy `Select` statement to modify.
            alias: The `AliasedClass` for the primary entity of the query.

        Returns:
            The (potentially) modified `Select` statement.
        """
        return statement
