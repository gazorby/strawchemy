"""SQLAlchemy query scope and inspection utilities.

This module provides classes for managing and inspecting the context of SQLAlchemy
queries generated from GraphQL queries. It includes `AliasContext` for maintaining
the state and context during transpilation, and `NodeInspect` for inspecting
individual query nodes within a scope.

Key Classes:
    - AliasContext: Manages the context for building SQLAlchemy queries, including
      aliases, selected columns, and relationships.
    - NodeInspect: Provides inspection capabilities for SQLAlchemy query nodes,
      handling function mapping, foreign key resolution, and property access.
    - AggregationFunctionInfo: A helper class that encapsulates information about how a SQL function
      should be applied in query building.

These classes are primarily used by the `Transpiler` class to build SQL queries
from GraphQL queries, ensuring correct alias handling, relationship management,
and function application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias

from sqlalchemy import ColumnElement, FromClause, Function, Label, Select, func, inspect
from sqlalchemy import cast as sqla_cast
from sqlalchemy import distinct as sqla_distinct
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapper, MapperProperty, QueryableAttribute, RelationshipProperty, aliased
from typing_extensions import Self, override

from strawchemy.constants import NODES_KEY
from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.dto.strawberry import GraphQLFieldDefinition, QueryNode
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.exceptions import TranspilingError
from strawchemy.repository.typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql.elements import KeyedColumnElement

    from strawchemy.repository.typing import DeclarativeSubT, FunctionGenerator, RelationshipSide
    from strawchemy.typing import QueryNodeType, SupportedDialect

__all__ = ("AliasContext",)

_FunctionVisitor: TypeAlias = "Callable[[Function[Any]], ColumnElement[Any]]"


def require_corresponding_column(selectable: FromClause, label: KeyedColumnElement[Any]) -> KeyedColumnElement[Any]:
    """Re-projects ``label`` onto ``selectable`` by object identity (name-independent).

    The returned column is used directly in the outer SELECT and the executor's column map;
    it is intentionally NOT re-labelled, because labelling a corresponded anonymous column
    yields a non-deterministic, object-id-embedded name. The executor reads values by column
    object identity, so no label is required.

    Args:
        selectable: The FROM clause (lateral/CTE/subquery) exporting the column.
        label: The inner column/label object to locate on ``selectable``.

    Returns:
        The corresponding exported column on ``selectable``.

    Raises:
        TranspilingError: If ``selectable`` does not export a column corresponding to ``label``.
    """
    column = selectable.corresponding_column(label)
    if column is None:
        msg = f"aggregation re-projection: column {label!r} not exported by {selectable!r}"
        raise TranspilingError(msg)
    return column


@dataclass
class AggregationFunctionInfo:
    """Information about a SQL function and its application context.

    A helper class that encapsulates information about how a SQL function
    should be applied in query building. Used internally by NodeInspect
    to map GraphQL functions to their SQLAlchemy equivalents.

    Attributes:
        sqla_function: The SQLAlchemy function generator (e.g., func.count, func.sum)
        apply_on_column: Whether the function should be applied to a column
            True for functions like MIN, MAX that operate on columns
            False for functions like COUNT that can operate independently
    """

    functions_map: ClassVar[dict[str, FunctionGenerator]] = {
        "count": func.count,
        "min": func.min,
        "max": func.max,
        "sum": func.sum,
        "avg": func.avg,
        "stddev_samp": func.stddev_samp,
        "stddev_pop": func.stddev_pop,
        "var_samp": func.var_samp,
        "var_pop": func.var_pop,
    }
    sqla_function: FunctionGenerator
    apply_on_column: bool
    visitor: _FunctionVisitor | None = None

    @classmethod
    def from_name(cls, name: str, visitor: _FunctionVisitor | None = None) -> Self:
        """Creates an AggregationFunctionInfo instance from a function name.

        Looks up the provided `name` in the `cls.functions_map` to find the
        corresponding SQLAlchemy function generator. It determines if the function
        typically applies to a column (e.g., MIN, MAX) or can operate on a wildcard
        (e.g., COUNT).

        Args:
            name: The name of the aggregation function (e.g., "count", "min").
            visitor: An optional callable to transform the generated SQLAlchemy
                function expression.

        Returns:
            An instance of `AggregationFunctionInfo` configured for the named function.

        Raises:
            TranspilingError: If the `name` is not a known function.
        """
        if name not in cls.functions_map:
            msg = f"Unknown function {name}"
            raise TranspilingError(msg)
        apply_on_column = name != "count"
        return cls(sqla_function=cls.functions_map[name], apply_on_column=apply_on_column, visitor=visitor)

    def apply(self, *args: QueryableAttribute[Any] | ColumnElement[Any]) -> ColumnElement[Any]:
        """Applies the configured SQLAlchemy function to the given arguments.

        Constructs a SQLAlchemy function call using `self.sqla_function` and
        the provided `args`. If a `visitor` was configured for this instance,
        it is applied to the resulting function expression.

        Args:
            *args: The arguments to pass to the SQLAlchemy function. These are
                typically column expressions or other SQL elements.

        Returns:
            A SQLAlchemy `ColumnElement` representing the function call.
        """
        func = self.sqla_function(*args)
        if self.visitor:
            func = self.visitor(func)
        return func


@dataclass(frozen=True)
class _ColumnTransform:
    """Represents a transformed SQLAlchemy column attribute.

    This dataclass typically stores a `QueryableAttribute` that has undergone
    some transformation, such as being labeled or having a function applied
    (e.g., for JSON extraction). Instances are usually created via its
    classmethod constructors like `_new` (for labeling) or `extract_json`.

    The main purpose is to encapsulate the transformed attribute along with
    the context (via `AliasContext` and `QueryNodeType`) in which the
    transformation occurred, ensuring unique naming and dialect-specific
    handling.

    Attributes:
        attribute: The transformed `QueryableAttribute`.
        node: The query node this transformed attribute belongs to.
    """

    attribute: QueryableAttribute[Any]
    node: QueryNodeType

    @classmethod
    def _new(cls, attribute: Function[Any] | QueryableAttribute[Any], node: QueryNodeType) -> Self:
        """Creates a ColumnTransform by labeling an attribute or function.

        This factory method takes a SQLAlchemy `Function` or `QueryableAttribute`
        and applies an anonymous label to it, pairing it with its query node.

        Args:
            attribute: The SQLAlchemy function or attribute to be labeled.
            node: The query node associated with this attribute/function.

        Returns:
            A new `ColumnTransform` instance with the labeled attribute.
        """
        return cls(attribute.label(None), node)

    @classmethod
    def extract_json(cls, attribute: QueryableAttribute[Any], node: QueryNodeType, scope: AliasContext[Any]) -> Self:
        """Creates a ColumnTransform for extracting a value from a JSON column.

        This factory method generates a SQLAlchemy expression to extract a value
        from a JSON-like column (`attribute`) based on a JSON path specified in
        `node.metadata.data.json_path`. The extraction logic is dialect-specific:

        - For PostgreSQL (`scope.dialect == "postgresql"`), it uses
          `func.jsonb_path_query_first`, coalescing to an empty JSONB object (`{}`)
          if the path does not exist or the value is null.
        - For other dialects, it uses the `->` operator (common for JSON extraction),
          coalescing to an empty JSON object (`func.json_object()`) on null/missing.

        The resulting transformation is then labeled using `cls._new` to ensure
        a unique column name in the query.

        Args:
            attribute: The `QueryableAttribute` representing the JSON column.
            node: The query node containing metadata, specifically the `json_path`
                under `node.metadata.data.json_path`.
            scope: The current query scope, used for dialect-specific logic and
                for labeling the transformed attribute.

        Returns:
            A new `ColumnTransform` instance with the JSON extraction expression,
            appropriately labeled.
        """
        if scope.dialect == "postgresql":
            transform = func.coalesce(
                func.jsonb_path_query_first(attribute, sqla_cast(node.metadata.data.json_path, postgresql.JSONPATH)),
                sqla_cast({}, postgresql.JSONB),
            )
        else:
            transform = func.coalesce(attribute.op("->")(node.metadata.data.json_path), func.json_object())
        return cls._new(transform, node)


class _NodeInspect:
    """Reads one query node against an ``AliasContext``.

    Bundles a node with its scope and exposes the node-level derivations the
    planning passes need: aliased columns and foreign keys, aggregation-function
    expressions, the node's mapper, and the scope-unique key/name used to label
    columns. Stateless beyond the ``(node, scope)`` pair; obtained via
    ``AliasContext.inspect(node)``.

    Attributes:
        node: The query node being inspected.
        scope: The scope resolving the node's aliases.
    """

    def __init__(self, node: QueryNodeType, scope: AliasContext[Any]) -> None:
        """Binds the helper to a node and its scope.

        Args:
            node: The query node to inspect.
            scope: The scope resolving the node's aliases.
        """
        self.node = node
        self.scope = scope

    def _foreign_keys_selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        """Returns the local FK columns of the node's child relationships.

        For each child that is a relationship, its local (parent-side) foreign-key
        columns are adapted to ``alias``. These keep the parent side of a relation
        selectable so a later join can resolve.

        Args:
            alias: The alias to adapt the FK columns to; defaults to the node's
                parent alias when ``None``.

        Returns:
            The aliased local foreign-key ``QueryableAttribute`` list.
        """
        selected_fks: list[QueryableAttribute[Any]] = []
        alias_insp = inspect(alias or self.scope.alias_from_relation_node(self.node, "parent"))
        for child in self.node.children:
            if not child.value.is_relation or not isinstance(child.value.model_field.property, RelationshipProperty):
                continue
            for column in child.value.model_field.property.local_columns:
                if column.key is None:
                    continue
            selected_fks.extend(
                [
                    alias_insp.mapper.attrs[column.key].class_attribute.adapt_to_entity(alias_insp)
                    for column in child.value.model_field.property.local_columns
                    if column.key is not None
                ]
            )
        return selected_fks

    def _transform_column(
        self, node: QueryNodeType, attribute: QueryableAttribute[Any]
    ) -> QueryableAttribute[Any] | _ColumnTransform:
        """Wraps a column in a JSON-extraction transform when the node requires one.

        When ``node.metadata.data.json_path`` is set, returns a ``ColumnTransform``
        extracting that path; otherwise returns the attribute unchanged.

        Args:
            node: The node supplying the optional JSON path.
            attribute: The column attribute to possibly transform.

        Returns:
            A ``ColumnTransform`` when a JSON path applies, else the attribute.
        """
        transform: _ColumnTransform | None = None
        if node.metadata.data.json_path:
            transform = _ColumnTransform.extract_json(attribute, node, self.scope)
        return attribute if transform is None else transform

    @property
    def children(self) -> list[_NodeInspect]:
        """The node's children, each wrapped in a ``_NodeInspect`` over the same scope."""
        return [_NodeInspect(child, self.scope) for child in self.node.children]

    @property
    def value(self) -> GraphQLFieldDefinition:
        """The node's ``GraphQLFieldDefinition`` (shortcut for ``self.node.value``)."""
        return self.node.value

    @property
    def mapper(self) -> Mapper[Any]:
        """The SQLAlchemy ``Mapper`` for the node's model.

        Taken from the model field's relationship property when the node is a
        mapped field, otherwise from the node's model directly (e.g. a root node).
        """
        if self.value.has_model_field:
            return self.value.model_field.property.mapper.mapper
        return self.value.model.__mapper__

    @property
    def key(self) -> str:
        """The node's base label key.

        Composed as an optional function-name prefix plus a suffix that is the
        table name for a root node or the model-field key otherwise.

        Returns:
            The label key for the node.
        """
        prefix = f"{function.function}_" if (function := self.value.function()) else ""
        if self.node.is_root:
            suffix = self.value.model.__tablename__
        else:
            suffix = self.value.model_field.key if self.value.has_model_field else ""
        return f"{prefix}{suffix}"

    @property
    def name(self) -> str:
        """The node's key, qualified by its parent's key when nested.

        Returns ``"<parent key>__<key>"`` when the node has a parent with a key,
        otherwise just ``key`` — keeping labels unique across nesting levels.

        Returns:
            The qualified label name.
        """
        if self.node.parent and (parent_key := _NodeInspect(self.node.parent, self.scope).key):
            return f"{parent_key}__{self.key}"
        return self.key

    @property
    def is_data_root(self) -> bool:
        """Whether the node is the data root of the query.

        True when the node is the root node, or — in a root-aggregations query —
        the ``NODES_KEY`` collection directly under the root. This is the entity
        collection that shares the root alias (e.g. the items listed alongside a
        root-level total count).

        Returns:
            True if the node is a data root.
        """
        return bool(
            (
                self.node.graph_metadata.metadata.root_aggregations
                and self.value.name == NODES_KEY
                and self.node.parent
                and self.node.parent.is_root
            )
            or self.node.is_root
        )

    def output_functions(
        self,
        alias: AliasedClass[Any],
        visit_func: _FunctionVisitor = lambda func: func,
    ) -> dict[QueryNodeType, Label[Any]]:
        """Builds the labelled aggregation-function columns for projection.

        For a column-applied function (e.g. MIN, MAX) each argument child is
        adapted to ``alias`` and the function applied per argument; for a
        column-less function (e.g. COUNT) the function is built once on the node
        itself. ``visit_func`` post-processes each expression before labelling
        (e.g. wrapping it in ``.over()`` for a window function).

        Args:
            alias: The alias to adapt function arguments to.
            visit_func: Transform applied to each function expression before
                labelling; identity by default.

        Returns:
            A mapping of function/argument node to its anonymously labelled column.
        """
        functions: dict[QueryNodeType, Label[Any]] = {}
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function, visitor=visit_func)
        if function_info.apply_on_column:
            for arg_child in self.children:
                arg = self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(
                    inspect(alias)
                )
                functions[arg_child.node] = function_info.apply(arg).label(None)
        else:
            functions[self.node] = visit_func(function_info.sqla_function()).label(None)
        return functions

    def filter_function(
        self, alias: AliasedClass[Any], distinct: bool | None = None
    ) -> tuple[QueryNodeType, Label[Any]]:
        """Builds the labelled aggregation-function column for a WHERE predicate.

        Like ``output_functions`` but returns a single function: its arguments are
        the node's children adapted to ``alias``, wrapped in SQLAlchemy
        ``distinct()`` when ``distinct`` is set. The associated node is the sole
        argument child when there is exactly one, otherwise the node itself.

        Args:
            alias: The alias to adapt function arguments to.
            distinct: Whether to wrap the arguments in ``distinct()``.

        Returns:
            The associated node and its anonymously labelled function column.
        """
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function)
        function_args = []
        argument_attributes = [
            self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(inspect(alias))
            for arg_child in self.children
        ]
        function_args = (sqla_distinct(*argument_attributes),) if distinct else argument_attributes
        function_node = self.children[0].node if len(self.children) == 1 else self.node
        return function_node, function_info.apply(*function_args).label(None)

    def columns(
        self, alias: AliasedClass[Any] | None = None
    ) -> tuple[list[QueryableAttribute[Any]], list[_ColumnTransform]]:
        """Splits the node's scalar children into plain columns and transforms.

        Each non-relation, non-computed child is resolved to its aliased attribute;
        JSON-path children become ``ColumnTransform`` entries, the rest plain
        columns. The node's primary-key attributes are appended to the columns
        unless already selected, so the row is always identifiable.

        Args:
            alias: The alias to adapt columns to; inferred by the scope when ``None``.

        Returns:
            The plain ``QueryableAttribute`` columns and the ``ColumnTransform`` list.
        """
        columns: list[QueryableAttribute[Any]] = []
        transforms: list[_ColumnTransform] = []
        property_set: set[MapperProperty[Any]] = set()
        for child in self.node.children:
            if not child.value.is_relation and not child.value.is_computed:
                aliased = self.scope.aliased_attribute(child, alias)
                property_set.add(aliased.property)
                aliased = self._transform_column(child, aliased)
                if isinstance(aliased, _ColumnTransform):
                    transforms.append(aliased)
                else:
                    columns.append(aliased)

        # Ensure id columns are added
        id_attributes = self.scope.aliased_id_attributes(self.node, alias)
        columns.extend(attribute for attribute in id_attributes if attribute.property not in property_set)
        return columns, transforms

    def foreign_key_columns(
        self, side: RelationshipSide, alias: AliasedClass[Any] | None = None
    ) -> list[QueryableAttribute[Any]]:
        """Returns the foreign-key columns of the node's relationship, adapted to an alias.

        ``side`` picks which end: ``"parent"`` yields the local columns,
        ``"target"`` the remote columns. They are adapted to ``alias``, or to the
        alias inferred from the node and side when ``None``.

        Args:
            side: Which end of the relationship to read keys from (``"parent"`` or ``"target"``).
            alias: The alias to adapt the FK columns to; inferred when ``None``.

        Returns:
            The aliased foreign-key ``QueryableAttribute`` list.

        Raises:
            AssertionError: If the node's model field is not a ``RelationshipProperty``.
        """
        alias_insp = inspect(alias or self.scope.alias_from_relation_node(self.node, side))
        relationship = self.node.value.model_field.property
        assert isinstance(relationship, RelationshipProperty)
        columns = relationship.local_columns if side == "parent" else relationship.remote_side
        return [
            alias_insp.mapper.attrs[column.key].class_attribute.adapt_to_entity(alias_insp)
            for column in columns
            if column.key is not None
        ]

    def selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        """Returns every attribute to select for the node.

        The node's plain columns (from ``columns``; transforms are excluded) plus
        the local foreign keys of its child relationships (from
        ``_foreign_keys_selection``), so child relations can later be joined.

        Args:
            alias: The alias to adapt attributes to; inferred when ``None``.

        Returns:
            The columns to select, including the relationship foreign keys.
        """
        columns, _ = self.columns(alias)
        return [*columns, *self._foreign_keys_selection(alias)]


class AliasContext(Generic[DeclarativeT]):
    """The per-query scope mapping GraphQL query nodes to SQLAlchemy aliases.

    Holds the root alias for one model level plus a shared map from
    ``(node, relationship side)`` to the aliased class used for it, so every
    reference to a column or relationship resolves to a consistent alias and the
    generated SQL stays free of naming conflicts.

    A scope is mutable and hierarchical:

    - ``replace`` re-roots it in place, used when the query is wrapped in a
      pagination/distinct subquery.
    - ``sub`` derives a child scope for a related collection, sharing this
      scope's alias map and inspector so aliases stay consistent across levels.

    ``PlanContext`` holds the active scope as its ``aliases`` field; the planning
    passes resolve attributes and build expressions through it.
    """

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: SupportedDialect,
        root_alias: AliasedClass[DeclarativeBase] | None = None,
        parent: AliasContext[Any] | None = None,
        alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] | None = None,
        inspector: SQLAlchemyInspector | None = None,
    ) -> None:
        """Initializes the AliasContext.

        Sets up the initial state for the query scope, including the root model,
        dialect, parent scope (if any), and alias mappings.

        Args:
            model: The primary SQLAlchemy model class for this scope.
            dialect: The SQL dialect being targeted (e.g., "postgresql", "sqlite").
            root_alias: An optional pre-defined `AliasedClass` for the root model.
                If None, a new alias is created from the `model`.
            parent: An optional parent `AliasContext` if this is a nested scope
                (e.g., for a subquery or relationship).
            alias_map: An optional dictionary to pre-populate the mapping of
                (query node, relationship side) tuples to `AliasedClass` instances.
            inspector: An optional `SQLAlchemyInspector` instance. If None, a new
                one is created using the model's registry.
        """
        self._parent: AliasContext[Any] | None = parent
        self._root_alias = (
            root_alias if root_alias is not None else aliased(model.__mapper__, name=model.__tablename__, flat=True)
        )
        self._node_alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] = alias_map or {}
        self._inspector = inspector or SQLAlchemyInspector([model.registry])

        self.dialect: SupportedDialect = dialect
        self.model = model
        self.level: int = self._parent.level + 1 if self._parent else 0

    @property
    def is_root(self) -> bool:
        """Checks if the current query scope is the root scope.

        A scope is considered the root scope if it does not have a parent scope.

        Returns:
            True if this is the root scope, False otherwise.
        """
        return self._parent is None

    @property
    def root_alias(self) -> AliasedClass[Any]:
        """The aliased class this scope is currently rooted on."""
        return self._root_alias

    def inspect(self, node: QueryNodeType) -> _NodeInspect:
        """Returns a node-inspection helper bound to this scope."""
        return _NodeInspect(node, self)

    def alias_from_relation_node(self, node: QueryNodeType, side: RelationshipSide) -> AliasedClass[Any]:
        """Returns the aliased class for one side of a relation node.

        The alias is created on first use and cached in the scope's alias map, so
        repeated lookups for the same ``(node, side)`` return the same alias. The
        root alias is returned when the node is the data root (or, for ``"parent"``,
        when its parent is).

        Args:
            node: The relation node to resolve an alias for.
            side: Which end of the relationship to alias (``"parent"`` or ``"target"``).

        Returns:
            The aliased class for that side of the relation.

        Raises:
            TranspilingError: If ``node`` is not a relation node.
        """
        node_inspect = self.inspect(node)
        if (side == "parent" and node.parent and self.inspect(node.parent).is_data_root) or node_inspect.is_data_root:
            return self._root_alias
        if not node.value.is_relation:
            msg = "Node must be a relation node"
            raise TranspilingError(msg)
        attribute = node.value.model_field
        if (alias := self._node_alias_map.get((node, side))) is not None:
            return alias
        mapper = attribute.parent.mapper if side == "parent" else attribute.entity.mapper
        alias = aliased(mapper.class_, flat=True)
        self.set_relation_alias(node, side, alias)
        return alias

    def aliased_attribute(self, node: QueryNodeType, alias: AliasedClass[Any] | None = None) -> QueryableAttribute[Any]:
        """Adapts a node's model field to the alias it should use in the query.

        With an explicit ``alias`` the field is adapted to it directly. Otherwise
        the alias is inferred from the node's position: a column field adapts to
        its parent relation's target alias, while a relation field adapts to the
        parent alias and is then typed (``of_type``) onto its own target alias.

        Args:
            node: The query node whose model field is being resolved.
            alias: An explicit alias to adapt to; inferred from the node when ``None``.

        Returns:
            The adapted ``QueryableAttribute`` ready for use in SQL expressions.
        """
        model_field: QueryableAttribute[RelationshipProperty[Any]] = node.value.model_field
        if alias is not None:
            return model_field.adapt_to_entity(inspect(alias))
        parent = node.find_parent(lambda node: not node.value.is_computed, strict=True)
        if model_field.parent.is_aliased_class:
            return model_field
        if not node.value.is_relation:
            parent_alias = self.alias_from_relation_node(parent, "target")
            return model_field.adapt_to_entity(inspect(parent_alias))
        parent_alias = (
            self._root_alias if self.inspect(parent).is_data_root else self.alias_from_relation_node(parent, "target")
        )
        model_field = model_field.adapt_to_entity(inspect(parent_alias))
        child_alias = self.alias_from_relation_node(node, "target")
        return model_field.of_type(child_alias)

    def aliased_id_attributes(
        self, node: QueryNodeType, alias: AliasedClass[Any] | None = None
    ) -> list[QueryableAttribute[Any]]:
        """Returns a node's primary-key attributes, adapted to its alias.

        The PK columns come from the node's mapper (the root mapper for the root
        node). They are adapted to ``alias`` when given, otherwise to the root
        alias for the root node, or to the relation's target alias for a
        non-root node.

        Args:
            node: The node whose primary-key attributes are requested.
            alias: An explicit alias to adapt to; inferred from the node when ``None``.

        Returns:
            The aliased primary-key ``QueryableAttribute`` list.
        """
        # Get the appropriate mapper based on whether the node is root or not
        # For root nodes, use the root alias mapper, otherwise inspect the node to get its mapper
        mapper = inspect(self._root_alias).mapper if node.is_root else self.inspect(node).mapper

        # Get all primary key attributes from the mapper using SQLAlchemyInspector helper
        columns = SQLAlchemyInspector.pk_attributes(mapper)

        # If an explicit alias is provided, adapt all PK attributes to that alias
        # This is used when we need to reference PKs in a specific aliased context
        if alias is not None:
            return [pk_attribute.adapt_to_entity(inspect(alias)) for pk_attribute in columns]

        # For root nodes, adapt PK attributes to the root alias
        # This ensures proper referencing in the main query context
        if node.is_root:
            columns = [pk_attribute.adapt_to_entity(inspect(self._root_alias)) for pk_attribute in columns]
        else:
            # For non-root nodes, get the target alias for the relationship
            # and adapt PK attributes to that alias for proper joining
            parent_alias = self.alias_from_relation_node(node, "target")
            columns = [pk_attribute.adapt_to_entity(inspect(parent_alias)) for pk_attribute in columns]

        return columns

    def scoped_column(self, clause: Select[Any] | FromClause, column_name: str) -> ColumnElement[Any]:
        """Retrieves a column object from a SELECT or FROM clause by name.

        The original column is fetched from `clause.selected_columns` (for `Select`)
        or `clause.columns` (for `FromClause`). The column object is returned as-is:
        consumers reference it by object identity, so no relabelling is needed.

        Args:
            clause: The SQLAlchemy `Select` or `FromClause` object from which
                to retrieve the column.
            column_name: The name of the column to retrieve.

        Returns:
            The column object from the clause.
        """
        columns = clause.selected_columns if isinstance(clause, Select) else clause.columns
        return columns[column_name]

    def set_relation_alias(self, node: QueryNodeType, side: RelationshipSide, alias: AliasedClass[Any]) -> None:
        """Stores an alias for a specific relationship node and side.

        This method updates the internal `_node_alias_map` to associate the
        given `alias` with the tuple `(node, side)`. This map is used to
        retrieve previously established aliases for relationships, preventing
        redundant alias creation and ensuring consistency.

        Args:
            node: The `QueryNodeType` representing the relationship.
            side: The `RelationshipSide` ("parent" or "target") for which
                this alias applies.
            alias: The `AliasedClass` to store for this node and side.
        """
        self._node_alias_map[(node, side)] = alias

    def id_field_definitions(self, model: type[DeclarativeBase]) -> list[GraphQLFieldDefinition]:
        """Generates GraphQL field definitions for the ID attributes of a model.

        This method first gets the aliased ID attributes for the given `model`
        (treated as a root node for this purpose) using `self.aliased_id_attributes()`.
        Then, for each aliased ID attribute, it uses the scope's `_inspector`
        to create a `GraphQLFieldDefinition` suitable for read purposes.

        Args:
            model: The SQLAlchemy model class for which to generate ID field definitions.

        Returns:
            A list of `GraphQLFieldDefinition` objects for the model's ID fields.
        """
        root = QueryNode.root_node(model)
        return [
            GraphQLFieldDefinition.from_field(self._inspector.field_definition(pk, DTOConfig(Purpose.READ)))
            for pk in self.aliased_id_attributes(root)
        ]

    def replace(self, model: type[DeclarativeT] | None = None, alias: AliasedClass[Any] | None = None) -> None:
        """Re-roots this scope in place onto a new model and/or root alias.

        Mutates the current scope rather than deriving a child, so callers holding
        the same scope object (e.g. ``PlanContext.build_join``) observe the new
        root. Used at the pagination/distinct subquery boundary.

        Args:
            model: The model to root on, or ``None`` to keep the current one.
            alias: The root alias to use, or ``None`` to keep the current one.
        """
        if model is not None:
            self.model = model
        if alias is not None:
            self._root_alias = alias

    def sub(self, model: type[DeclarativeSubT], alias: AliasedClass[Any]) -> AliasContext[DeclarativeSubT]:
        """Derives a child scope rooted on a related model.

        The child shares this scope's alias map and inspector so aliases stay
        consistent across levels, and links back via ``parent`` (raising its
        ``level`` by one).

        Args:
            model: The related model the child scope is rooted on.
            alias: The root alias for the child scope.

        Returns:
            A new child ``AliasContext`` one level below this one.
        """
        return AliasContext(
            model=model,
            root_alias=alias,
            parent=self,
            alias_map=self._node_alias_map,
            inspector=self._inspector,
            dialect=self.dialect,
        )

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.model},{self.level}>"
