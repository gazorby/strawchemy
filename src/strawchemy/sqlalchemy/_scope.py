"""SQLAlchemy query scope and inspection utilities.

This module provides classes for managing and inspecting the context of SQLAlchemy
queries generated from GraphQL queries. It includes `QueryScope` for maintaining
the state and context during transpilation, and `NodeInspect` for inspecting
individual query nodes within a scope.

Key Classes:
    - QueryScope: Manages the context for building SQLAlchemy queries, including
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

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapper, MapperProperty, QueryableAttribute, RelationshipProperty, aliased
from sqlalchemy.orm.util import AliasedClass
from typing_extensions import Self, override

from sqlalchemy import ColumnElement, FromClause, Function, Label, Select, func, inspect
from sqlalchemy import cast as sqla_cast
from sqlalchemy import distinct as sqla_distinct
from strawchemy.constants import NODES_KEY
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.graph import Node
from strawchemy.strawberry.dto import GraphQLFieldDefinition, QueryNode

from .exceptions import TranspilingError
from .inspector import SQLAlchemyInspector
from .typing import DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql.elements import NamedColumn

    from strawchemy.strawberry.typing import QueryNodeType
    from strawchemy.typing import SupportedDialect

    from .typing import DeclarativeSubT, FunctionGenerator, RelationshipSide

__all__ = ("NodeInspect", "QueryScope")

_FunctionVisitor: TypeAlias = "Callable[[Function[Any]], ColumnElement[Any]]"


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
class ColumnTransform:
    """Represents a transformed SQLAlchemy column attribute.

    This dataclass typically stores a `QueryableAttribute` that has undergone
    some transformation, such as being labeled or having a function applied
    (e.g., for JSON extraction). Instances are usually created via its
    classmethod constructors like `_new` (for labeling) or `extract_json`.

    The main purpose is to encapsulate the transformed attribute along with
    the context (via `QueryScope` and `QueryNodeType`) in which the
    transformation occurred, ensuring unique naming and dialect-specific
    handling.

    Attributes:
        attribute: The transformed `QueryableAttribute`.
    """

    attribute: QueryableAttribute[Any]

    @classmethod
    def _new(
        cls, attribute: Function[Any] | QueryableAttribute[Any], node: QueryNodeType, scope: QueryScope[Any]
    ) -> Self:
        """Creates a ColumnTransform by labeling an attribute or function.

        This factory method takes a SQLAlchemy `Function` or `QueryableAttribute`
        and applies a unique label to it based on the `QueryNodeType` and `QueryScope`.
        The label is generated using `scope.key(node)`.

        Args:
            attribute: The SQLAlchemy function or attribute to be labeled.
            node: The query node associated with this attribute/function.
            scope: The current query scope, used for generating a unique key/label.

        Returns:
            A new `ColumnTransform` instance with the labeled attribute.
        """
        return cls(attribute.label(scope.key(node)))

    @classmethod
    def extract_json(cls, attribute: QueryableAttribute[Any], node: QueryNodeType, scope: QueryScope[Any]) -> Self:
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
        return cls._new(transform, node, scope)


class NodeInspect:
    """Inspection helper for SQLAlchemy query nodes.

    Provides functionality to inspect and process SQLAlchemy query nodes within a QueryScope context.
    Handles function mapping, foreign key resolution, and property access for query nodes.

    Attributes:
        node (QueryNodeType): The query node being inspected
        scope (QueryScope): The query scope providing context for inspection

    Key Responsibilities:
        - Maps GraphQL functions to corresponding SQL functions
        - Resolves foreign key relationships between nodes
        - Provides access to node properties and children
        - Generates SQL expressions for functions and selections
        - Handles column and ID selection for query building

    The class works closely with QueryScope to provide context-aware inspection capabilities
    and is primarily used by the Transpiler class to build SQL queries from GraphQL queries.

    Example:
        >>> node = QueryNodeType(...)
        >>> scope = QueryScope(...)
        >>> inspector = NodeInspect(node, scope)
        >>> inspector.functions(alias)  # Get SQL function expressions
        >>> inspector.columns_or_ids()  # Get columns or IDs for selection
    """

    def __init__(self, node: QueryNodeType, scope: QueryScope[Any]) -> None:
        """Initializes the NodeInspect helper.

        Args:
            node: The query node (`QueryNodeType`) to be inspected.
            scope: The `QueryScope` providing context for the inspection,
                such as aliases, dialect, and parent relationships.
        """
        self.node = node
        self.scope = scope

    def _foreign_keys_selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        """Selects local foreign key columns for child relationships of the current node.

        Iterates through the children of the current `self.node`. If a child
        represents a relationship (is_relation is True and model_field.property
        is a RelationshipProperty), it identifies the local columns involved in
        that relationship.

        These local columns (foreign keys on the parent side of the relationship)
        are then adapted to the provided `alias` (or an alias inferred from the
        parent node if `alias` is None).

        Args:
            alias: The `AliasedClass` to which the foreign key attributes should be
                adapted. If None, defaults to the alias of the parent of `self.node`.

        Returns:
            A list of `QueryableAttribute` objects representing the aliased
            local foreign key columns.
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
    ) -> QueryableAttribute[Any] | ColumnTransform:
        """Applies transformations to a column attribute if necessary.

        Currently, this method checks if the `node.metadata.data.json_path` is set.
        If it is, it applies a JSON extraction transformation using
        `ColumnTransform.extract_json`. Otherwise, it returns the original attribute.

        Args:
            node: The `QueryNodeType` providing metadata for potential transformations
                (e.g., JSON path).
            attribute: The `QueryableAttribute` to potentially transform.

        Returns:
            The transformed attribute (as a `ColumnTransform` instance) if a
            transformation was applied, or the original `QueryableAttribute` otherwise.
        """
        transform: ColumnTransform | None = None
        if node.metadata.data.json_path:
            transform = ColumnTransform.extract_json(attribute, node, self.scope)
        return attribute if transform is None else transform

    @property
    def children(self) -> list[NodeInspect]:
        """Provides `NodeInspect` instances for all children of the current node.

        Returns:
            A list of `NodeInspect` objects, each initialized with a child
            of `self.node` and the same `self.scope`.
        """
        return [NodeInspect(child, self.scope) for child in self.node.children]

    @property
    def value(self) -> GraphQLFieldDefinition:
        """The `GraphQLFieldDefinition` associated with the current node.

        This is a direct accessor to `self.node.value`.

        Returns:
            The `GraphQLFieldDefinition` of the current node.
        """
        return self.node.value

    @property
    def mapper(self) -> Mapper[Any]:
        """The SQLAlchemy `Mapper` for the model associated with the current node.

        If the node's value (`self.value`) has a `model_field` (e.g., it's an
        attribute of a model), it returns the mapper from that field's property.
        Otherwise (e.g., it's a root model type), it returns the mapper directly
        from `self.value.model`.

        Returns:
            The SQLAlchemy `Mapper` object.
        """
        if self.value.has_model_field:
            return self.value.model_field.property.mapper.mapper
        return self.value.model.__mapper__

    @property
    def key(self) -> str:
        """Generates a base key for the current node.

        The key is constructed based on whether the node represents a function,
        is a root node, or is a model field.
        - If it's a function, the function name is used as a prefix.
        - If it's a root node, the model's table name is used as a suffix.
        - If it's a model field, the field's key is used as a suffix.

        Returns:
            A string key representing the node.
        """
        prefix = f"{function.function}_" if (function := self.value.function()) else ""
        if self.node.is_root:
            suffix = self.value.model.__tablename__
        else:
            suffix = self.value.model_field.key if self.value.has_model_field else ""
        return f"{prefix}{suffix}"

    @property
    def name(self) -> str:
        """Generates a potentially qualified name for the current node.

        If the node has a parent, the name is constructed by prefixing the
        parent's key (obtained via `NodeInspect(self.node.parent, self.scope).key`)
        to the current node's `key`, separated by '__'.
        If there is no parent, it simply returns the node's `key`.
        This helps create unique names in nested structures.

        Returns:
            A string name, potentially qualified by its parent's key.
        """
        if self.node.parent and (parent_key := NodeInspect(self.node.parent, self.scope).key):
            return f"{parent_key}__{self.key}"
        return self.key

    @property
    def is_data_root(self) -> bool:
        """Determines if the current node acts as a data root in an aggregation query.

        A node is considered a data root if:
        - It's part of a query with root aggregations (`self.node.graph_metadata.metadata.root_aggregations` is True),
        - AND its field name is the standard 'nodes' key (`NODES_KEY`),
        - AND it has a parent node which is itself a root node (`self.node.parent.is_root`).
        Alternatively, if the node itself is marked as a root (`self.node.is_root`),
        it's also considered a data root.

        This is typically used to identify the primary entity collection within
        queries that involve aggregations at the root level (e.g., total count
        alongside a list of items).

        Returns:
            True if the node is a data root, False otherwise.
        """
        return (
            self.node.graph_metadata.metadata.root_aggregations
            and self.value.name == NODES_KEY
            and self.node.parent
            and self.node.parent.is_root
        ) or self.node.is_root

    def output_functions(
        self,
        alias: AliasedClass[Any],
        visit_func: _FunctionVisitor = lambda func: func,
    ) -> dict[QueryNodeType, Label[Any]]:
        """Generates labeled SQLAlchemy function expressions for output.

        This method processes the function defined in `self.value.function()`.
        It uses `AggregationFunctionInfo` to get the SQLAlchemy function.

        - If `apply_on_column` is True (e.g., MIN, MAX), it iterates through
          the children of the current node (which represent function arguments),
          adapts each child's model field to the given `alias`, applies the
          function, labels it with a unique key from the scope, and stores it.
        - If `apply_on_column` is False (e.g., COUNT), it applies the function
          (often to a wildcard or no specific column), labels it, and stores it.

        The `visit_func` can be used to further transform the generated
        SQLAlchemy function expression before labeling.

        Args:
            alias: The `AliasedClass` to which function arguments (if any)
                should be adapted.
            visit_func: An optional callable to transform the generated
                SQLAlchemy function expression before labeling. Defaults to an
                identity function.

        Returns:
            A dictionary mapping `QueryNodeType` (representing the function or
            its argument node) to the corresponding labeled SQLAlchemy
            function expression (`Label`).
        """
        functions: dict[QueryNodeType, Label[Any]] = {}
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function, visitor=visit_func)
        if function_info.apply_on_column:
            for arg_child in self.children:
                arg = self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(
                    inspect(alias)
                )
                functions[arg_child.node] = function_info.apply(arg).label(self.scope.key(arg_child.node))
        else:
            functions[self.node] = visit_func(function_info.sqla_function()).label(self.scope.key(self.node))
        return functions

    def filter_function(
        self, alias: AliasedClass[Any], distinct: bool | None = None
    ) -> tuple[QueryNodeType, Label[Any]]:
        """Generates a labeled SQLAlchemy function expression for use in filters.

        Similar to `output_functions`, but tailored for filter conditions.
        It retrieves the function using `AggregationFunctionInfo`.
        Arguments for the function are derived from the children of the current node,
        adapted to the given `alias`.
        If `distinct` is True, `sqlalchemy.distinct()` is applied to the arguments.

        The label for the function is determined by the scope key of either the
        first child (if there's only one, implying the function applies to that
        child's attribute) or the current node itself.

        Args:
            alias: The `AliasedClass` to adapt function arguments to.
            distinct: If True, applies `sqlalchemy.distinct()` to the function
                arguments. Defaults to None (no distinct).

        Returns:
            A tuple containing:
            - `QueryNodeType`: The node associated with the function (either the
              current node or its first child).
            - `Label[Any]`: The labeled SQLAlchemy function expression.
        """
        function_info = AggregationFunctionInfo.from_name(self.value.function(strict=True).function)
        function_args = []
        argument_attributes = [
            self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(inspect(alias))
            for arg_child in self.children
        ]
        function_args = (sqla_distinct(*argument_attributes),) if distinct else argument_attributes
        if len(self.children) == 1:
            function_node = self.children[0].node
            label_name = self.scope.key(function_node)
        else:
            function_node = self.node
            label_name = self.scope.key(self.node)
        return function_node, function_info.apply(*function_args).label(label_name)

    def columns(
        self, alias: AliasedClass[Any] | None = None
    ) -> tuple[list[QueryableAttribute[Any]], list[ColumnTransform]]:
        """Extracts regular columns and transformed columns for the current node.

        Iterates through the children of the current node (`self.node`).
        For each child that is not a relation and not a computed field:
        1. It gets the aliased attribute using `self.scope.aliased_attribute()`.
        2. It attempts to transform the column using `self._transform_column()`.
        3. If transformed (e.g., JSON extraction), it's added to the `transforms` list.
        4. Otherwise, the regular aliased attribute is added to the `columns` list.

        After processing all children, it ensures that ID attributes for the current
        node (obtained via `self.scope.aliased_id_attributes()`) are included in
        the `columns` list if they haven't been added already (to avoid duplicates
        if ID fields were explicitly requested).

        Args:
            alias: The `AliasedClass` to which the column attributes should be
                adapted. If None, the scope will infer the appropriate alias.

        Returns:
            A tuple containing two lists:
            - The first list contains `QueryableAttribute` objects for regular columns.
            - The second list contains `ColumnTransform` objects for transformed columns.
        """
        columns: list[QueryableAttribute[Any]] = []
        transforms: list[ColumnTransform] = []
        property_set: set[MapperProperty[Any]] = set()
        for child in self.node.children:
            if not child.value.is_relation and not child.value.is_computed:
                aliased = self.scope.aliased_attribute(child, alias)
                property_set.add(aliased.property)
                aliased = self._transform_column(child, aliased)
                if isinstance(aliased, ColumnTransform):
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
        """Retrieves foreign key columns for the current node's relationship.

        This method identifies the foreign key columns involved in the relationship
        represented by `self.node.value.model_field.property`. The `side` argument
        determines whether to fetch local columns (if `side` is "parent") or
        remote columns (if `side` is "child").

        The columns are then adapted to the provided `alias` (or an alias
        inferred from the node and side if `alias` is None).

        Args:
            side: Specifies which side of the relationship to get keys from
                ("parent" for local, "child" for remote).
            alias: The `AliasedClass` to adapt the foreign key attributes to.
                If None, an alias is inferred based on the node and relationship side.

        Returns:
            A list of `QueryableAttribute` objects representing the aliased
            foreign key columns.

        Raises:
            AssertionError: If `self.node.value.model_field.property` is not
                a `RelationshipProperty`.
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
        """Computes the full list of attributes to select for the current node.

        This combines the regular columns (and transformed columns, though only
        the `QueryableAttribute` part is returned here) obtained from `self.columns(alias)`
        with the foreign key columns needed for relationships, obtained from
        `self._foreign_keys_selection(alias)`.

        Args:
            alias: The `AliasedClass` to adapt attributes to. If None, aliases
                are inferred by the called methods.

        Returns:
            A list of `QueryableAttribute` objects representing all columns
            to be selected for the current node, including necessary foreign keys.
        """
        columns, _ = self.columns(alias)
        return [*columns, *self._foreign_keys_selection(alias)]


class QueryScope(Generic[DeclarativeT]):
    """Manages the context for building SQLAlchemy queries from GraphQL queries.

    The QueryScope class is responsible for maintaining the state and context
    required to transpile a GraphQL query into a SQLAlchemy query. It manages
    aliases for tables and relationships, tracks selected columns, and provides
    utilities for generating SQL expressions.

    Key Responsibilities:
        - Manages aliases for SQLAlchemy models and relationships.
        - Tracks selected columns and functions within the query.
        - Provides methods for generating aliased attributes and literal columns.
        - Supports nested scopes for subqueries and related entities.
        - Maintains a mapping of relationship properties to their aliases.
        - Generates unique names for columns and functions within the scope.

    The class is used by the Transpiler to build complex SQL queries by providing
    context-aware access to model attributes and relationships. It ensures that
    all parts of the query are correctly aliased and referenced, preventing
    naming conflicts and ensuring the query is valid.

    Example:
        >>> from sqlalchemy.orm import declarative_base
        >>> from sqlalchemy import Column, Integer, String
        >>> Base = declarative_base()
        >>> class User(Base):
        ...     __tablename__ = 'users'
        ...     id = Column(Integer, primary_key=True)
        ...     name = Column(String)
        >>> scope = QueryScope(User)
        >>> user_alias = scope.root_alias
        >>> print(user_alias.name)
        users
    """

    def __init__(
        self,
        model: type[DeclarativeT],
        dialect: SupportedDialect,
        root_alias: AliasedClass[DeclarativeBase] | None = None,
        parent: QueryScope[Any] | None = None,
        alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] | None = None,
        inspector: SQLAlchemyInspector | None = None,
    ) -> None:
        """Initializes the QueryScope.

        Sets up the initial state for the query scope, including the root model,
        dialect, parent scope (if any), and alias mappings.

        Args:
            model: The primary SQLAlchemy model class for this scope.
            dialect: The SQL dialect being targeted (e.g., "postgresql", "sqlite").
            root_alias: An optional pre-defined `AliasedClass` for the root model.
                If None, a new alias is created from the `model`.
            parent: An optional parent `QueryScope` if this is a nested scope
                (e.g., for a subquery or relationship).
            alias_map: An optional dictionary to pre-populate the mapping of
                (query node, relationship side) tuples to `AliasedClass` instances.
            inspector: An optional `SQLAlchemyInspector` instance. If None, a new
                one is created using the model's registry.
        """
        self._parent: QueryScope[Any] | None = parent
        self._root_alias = (
            root_alias if root_alias is not None else aliased(model.__mapper__, name=model.__tablename__, flat=True)
        )
        self._node_alias_map: dict[tuple[QueryNodeType, RelationshipSide], AliasedClass[Any]] = alias_map or {}
        self._node_keys: dict[QueryNodeType, str] = {}
        self._keys_set: set[str] = set()
        self._literal_name_counts: defaultdict[str, int] = defaultdict(int)
        self._literal_namespace: str = "__strawchemy"
        self._inspector = inspector or SQLAlchemyInspector([model.registry])

        self.dialect: SupportedDialect = dialect
        self.model = model
        self.level: int = self._parent.level + 1 if self._parent else 0
        self.columns: dict[QueryNodeType, NamedColumn[Any]] = {}
        self.selection_function_nodes: set[QueryNodeType] = set()
        self.order_by_function_nodes: set[QueryNodeType] = set()
        self.where_function_nodes: set[QueryNodeType] = set()

    def _add_scope_id(self, name: str) -> str:
        return name if self.is_root else f"{name}_{self.level}"

    def _node_key(self, node: QueryNodeType) -> str:
        if name := self._node_keys.get(node):
            return name
        node_inspect = self.inspect(node)
        scoped_name = node_inspect.name
        parent_prefix = ""

        for parent in node.iter_parents():
            if scoped_name not in self._keys_set:
                self._node_keys[node] = scoped_name
                break
            parent_name = self.inspect(parent).name
            parent_prefix = f"{parent_prefix}__{parent_name}" if parent_prefix else parent_name
            scoped_name = f"{parent_prefix}__{node_inspect.key}"

        return scoped_name

    @property
    def referenced_function_nodes(self) -> set[QueryNodeType]:
        """Gets the set of query nodes that represent functions referenced in the query.

        This includes function nodes that are used in WHERE clauses and also
        selected for output, OR function nodes used in ORDER BY clauses.
        This helps in identifying all function calls that need to be part of
        the generated query.

        Returns:
            A set of `QueryNodeType` objects representing referenced functions.
        """
        return (self.where_function_nodes & self.selection_function_nodes) | self.order_by_function_nodes

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
        return self._root_alias

    def inspect(self, node: QueryNodeType) -> NodeInspect:
        return NodeInspect(node, self)

    def alias_from_relation_node(self, node: QueryNodeType, side: RelationshipSide) -> AliasedClass[Any]:
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
        alias = aliased(mapper.class_, name=self.key(node), flat=True)
        self.set_relation_alias(node, side, alias)
        return alias

    def aliased_attribute(self, node: QueryNodeType, alias: AliasedClass[Any] | None = None) -> QueryableAttribute[Any]:
        """Adapts a model field to an aliased entity for query building.

        This method is a core component of the GraphQL to SQL transpilation process,
        handling the adaptation of model fields to their aliased representations in
        the generated SQL query. It manages both explicit aliases and inferred aliases
        based on parent-child relationships in the query structure.

        The method works in conjunction with other QueryScope methods to ensure
        consistent alias handling across the query:
        - Uses alias_from_relation_node for relationship traversal
        - Integrates with aliased_id_attributes for primary key handling
        - Supports the overall query building process in the Transpiler

        Args:
            node: The SQLAlchemy query node containing the model field to be aliased.
                Must be a valid query node with a model field reference.
            alias: An optional explicit alias to use for adaptation. If None, the alias
                will be inferred based on the node's position in the query structure.

        Returns:
            QueryableAttribute[Any]: The adapted attribute ready for use in SQL
            expressions. The attribute will be properly aliased according to the
            query context.

        Raises:
            AttributeError: If the node does not have a valid model field reference.
            TranspilingError: If there are issues with the node's relationship structure.

        Example:
            >>> node = QueryNodeType(...)  # Node with model field reference
            >>> scope = QueryScope(User)  # Query scope for User model
            >>> # Get attribute with explicit alias
            >>> attr = scope.aliased_attribute(node, aliased(User))
            >>> # Get attribute with inferred alias
            >>> attr = scope.aliased_attribute(node)
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
        """Retrieves aliased primary key (ID) attributes for a given node.

        This method determines the correct mapper for the node (root mapper for
        root nodes, node's own mapper otherwise) and fetches its primary key
        attributes using `SQLAlchemyInspector.pk_attributes()`.

        The retrieved PK attributes are then adapted to an appropriate alias:
        - If an explicit `alias` is provided, all PKs are adapted to it.
        - If the `node` is the root of the query, PKs are adapted to the scope's
          `_root_alias`.
        - For non-root nodes (typically representing relationships), PKs are
          adapted to the target alias of that relationship, obtained via
          `self.alias_from_relation_node(node, "target")`.

        This ensures that ID columns are correctly referenced in the query,
        whether for direct selection or for joins.

        Args:
            node: The `QueryNodeType` for which to get aliased ID attributes.
            alias: An optional explicit `AliasedClass` to adapt the ID attributes to.
                If None, the alias is inferred based on the node's context.

        Returns:
            A list of `QueryableAttribute` objects representing the aliased
            primary key attributes.
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

    def scoped_column(self, clause: Select[Any] | FromClause, column_name: str) -> Label[Any]:
        """Retrieves a column from a SELECT or FROM clause and labels it with a scope-specific ID.

        This is used to ensure that columns selected from subqueries or CTEs
        have unique names within the current query scope. The original column
        is fetched from the `clause.selected_columns` (for `Select`) or
        `clause.columns` (for `FromClause`) and then labeled using `_add_scope_id`
        to append a scope level identifier if not in the root scope.

        Args:
            clause: The SQLAlchemy `Select` or `FromClause` object from which
                to retrieve the column.
            column_name: The name of the column to retrieve and label.

        Returns:
            A `Label` object representing the scope-labeled column.
        """
        columns = clause.selected_columns if isinstance(clause, Select) else clause.columns
        return columns[column_name].label(self._add_scope_id(column_name))

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

    def key(self, element: str | QueryNodeType) -> str:
        """Generates a unique key for a query element or node.

        The key is used to uniquely identify elements within the query scope, ensuring
        proper referencing and preventing naming conflicts. The key generation strategy
        differs based on the input type:

        - For QueryNodeType: Generates a scoped name based on the node's position
          in the query structure, incorporating parent relationships and function prefixes
        - For string elements: Creates a unique name by appending a counter to prevent
          collisions with identical names

        Args:
            element: The element to generate a key for. Can be either:
                - A QueryNodeType: A node in the query structure
                - A string: A literal element name

        Returns:
            str: A unique key string that identifies the element within the query scope.
                 The key is scoped to the current query level to maintain uniqueness
                 across nested scopes.

        Example:
            >>> scope = QueryScope(User)
            >>> node = QueryNodeType(...)
            >>> scope.key(node)  # Returns a unique key for the node
            >>> scope.key("column_name")  # Returns a unique key for the literal
        """
        if isinstance(element, Node):
            scoped_name = self._node_key(element)
        else:
            scoped_name = f"{self._literal_namespace}_{element}_{self._literal_name_counts[element]}"
            self._literal_name_counts[element] += 1
        self._keys_set.add(scoped_name)
        return self._add_scope_id(scoped_name)

    def replace(
        self,
        model: type[DeclarativeT] | None = None,
        alias: AliasedClass[Any] | None = None,
    ) -> None:
        if model is not None:
            self.model = model
        if alias is not None:
            self._root_alias = alias

    def sub(self, model: type[DeclarativeSubT], alias: AliasedClass[Any]) -> QueryScope[DeclarativeSubT]:
        return QueryScope(
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
