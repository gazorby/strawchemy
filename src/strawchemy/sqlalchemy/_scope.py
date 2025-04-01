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
    - _FunctionInfo: A helper class that encapsulates information about how a SQL function
      should be applied in query building.

These classes are primarily used by the `Transpiler` class to build SQL queries
from GraphQL queries, ensuring correct alias handling, relationship management,
and function application.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NamedTuple, override

from sqlalchemy import Function, Label, func, inspect, literal_column
from sqlalchemy import distinct as sqla_distinct
from sqlalchemy.orm import DeclarativeBase, Mapper, MapperProperty, QueryableAttribute, RelationshipProperty, aliased
from sqlalchemy.orm.util import AliasedClass
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.graphql.constants import NODES_KEY
from strawchemy.graphql.dto import GraphQLFieldDefinition, QueryNode

from .exceptions import TranspilingError
from .inspector import SQLAlchemyInspector
from .typing import DeclarativeT, SQLAlchemyQueryNode

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql.elements import NamedColumn

    from .typing import DeclarativeSubT, FunctionGenerator, RelationshipSide, SQLAlchemyOrderByNode, SQLAlchemyQueryNode

__all__ = ("NodeInspect", "QueryScope")


class _FunctionInfo(NamedTuple):
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

    sqla_function: FunctionGenerator
    apply_on_column: bool


class NodeInspect:
    """Inspection helper for SQLAlchemy query nodes.

    Provides functionality to inspect and process SQLAlchemy query nodes within a QueryScope context.
    Handles function mapping, foreign key resolution, and property access for query nodes.

    Attributes:
        node (SQLAlchemyQueryNode): The query node being inspected
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
        >>> node = SQLAlchemyQueryNode(...)
        >>> scope = QueryScope(...)
        >>> inspector = NodeInspect(node, scope)
        >>> inspector.functions(alias)  # Get SQL function expressions
        >>> inspector.columns_or_ids()  # Get columns or IDs for selection
    """

    sqla_functions_map: ClassVar[dict[str, FunctionGenerator]] = {
        "count": func.count,
        "min": func.min,
        "max": func.max,
        "sum": func.sum,
        "avg": func.avg,
        "stddev": func.stddev,
        "stddev_samp": func.stddev_samp,
        "stddev_pop": func.stddev_pop,
        "variance": func.variance,
        "var_samp": func.var_samp,
        "var_pop": func.var_pop,
    }

    def __init__(self, node: SQLAlchemyQueryNode, scope: QueryScope[Any]) -> None:
        self.node = node
        self.scope = scope

    @classmethod
    def _function_info(cls, name: str) -> _FunctionInfo:
        if name not in cls.sqla_functions_map:
            msg = f"Unknown function {name}"
            raise TranspilingError(msg)
        apply_on_column = True
        if name == "count":
            apply_on_column = False
        return _FunctionInfo(sqla_function=cls.sqla_functions_map[name], apply_on_column=apply_on_column)

    def _foreign_keys(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
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

    @property
    def children(self) -> list[NodeInspect]:
        return [NodeInspect(child, self.scope) for child in self.node.children]

    @property
    def value(self) -> GraphQLFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]:
        return self.node.value

    @property
    def mapper(self) -> Mapper[Any]:
        if self.value.has_model_field:
            return self.value.model_field.property.mapper.mapper
        return self.value.model.__mapper__

    @property
    def key(self) -> str:
        prefix = f"{function.function}_" if (function := self.value.function()) else ""
        if self.node.is_root:
            suffix = self.value.model.__tablename__
        else:
            suffix = self.value.model_field.key if self.value.has_model_field else ""
        return f"{prefix}{suffix}"

    @property
    def name(self) -> str:
        if self.node.parent and (parent_key := NodeInspect(self.node.parent, self.scope).key):
            return f"{parent_key}__{self.key}"
        return self.key

    @property
    def is_data_root(self) -> bool:
        return (
            self.node.query_metadata.root_aggregations
            and self.value.name == NODES_KEY
            and self.node.parent
            and self.node.parent.is_root
        ) or self.node.is_root

    def output_functions(
        self,
        alias: AliasedClass[Any],
        visit_func: Callable[[Function[Any]], Any] = lambda func: func,
    ) -> dict[SQLAlchemyQueryNode, Label[Any]]:
        functions: dict[SQLAlchemyQueryNode, Label[Any]] = {}
        function_info = self._function_info(self.value.function(strict=True).function)
        sql_func = function_info.sqla_function
        if function_info.apply_on_column:
            for arg_child in self.children:
                arg = self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(
                    inspect(alias)
                )
                functions[arg_child.node] = visit_func(sql_func(arg)).label(self.scope.key(arg_child.node))
        else:
            functions[self.node] = visit_func(sql_func()).label(self.scope.key(self.node))
        return functions

    def filter_function(
        self, alias: AliasedClass[Any], distinct: bool | None = None
    ) -> tuple[SQLAlchemyQueryNode, Label[Any]]:
        function_info = self._function_info(self.value.function(strict=True).function)
        sql_func = function_info.sqla_function
        function_arg = []
        argument_attributes = [
            self.mapper.attrs[arg_child.value.model_field_name].class_attribute.adapt_to_entity(inspect(alias))
            for arg_child in self.children
        ]
        function_arg = (sqla_distinct(*argument_attributes),) if distinct else argument_attributes
        if len(self.children) == 1:
            function_node = self.children[0].node
            label_name = self.scope.key(function_node)
        else:
            function_node = self.node
            label_name = self.scope.key(self.node)
        return function_node, sql_func(*function_arg).label(label_name)

    def columns(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        columns: list[QueryableAttribute[Any]] = []
        property_set: set[MapperProperty[Any]] = set()
        for child in self.node.children:
            if not child.value.is_relation and not child.value.is_computed:
                aliased = self.scope.aliased_attribute(child, alias)
                columns.append(aliased)
                property_set.add(aliased.property)

        id_attributes = self.scope.aliased_id_attributes(self.node, alias)
        # Ensure id columns are added
        columns.extend(attribute for attribute in id_attributes if attribute.property not in property_set)
        return columns

    def selection(self, alias: AliasedClass[Any] | None = None) -> list[QueryableAttribute[Any]]:
        return [*self.columns(alias), *self._foreign_keys(alias)]


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
        root_alias: AliasedClass[DeclarativeBase] | None = None,
        parent: QueryScope[Any] | None = None,
        alias_map: dict[tuple[SQLAlchemyQueryNode, RelationshipSide], AliasedClass[Any]] | None = None,
        inspector: SQLAlchemyInspector | None = None,
    ) -> None:
        self._parent: QueryScope[Any] | None = parent
        self._root_alias = (
            root_alias if root_alias is not None else aliased(model.__mapper__, name=model.__tablename__, flat=True)
        )
        self._node_alias_map: dict[tuple[SQLAlchemyQueryNode, RelationshipSide], AliasedClass[Any]] = alias_map or {}
        self._node_keys: dict[SQLAlchemyQueryNode, str] = {}
        self._keys_set: set[str] = set()
        self._literal_name_counts: defaultdict[str, int] = defaultdict(int)
        self._inspector = inspector or SQLAlchemyInspector([model.registry])

        self.model = model
        self.level: int = self._parent.level + 1 if self._parent else 0
        self.columns: dict[SQLAlchemyQueryNode, NamedColumn[Any]] = {}
        self.selected_columns: list[NamedColumn[Any] | QueryableAttribute[Any]] = []
        self.selection_function_nodes: set[SQLAlchemyQueryNode] = set()
        self.order_by_function_nodes: set[SQLAlchemyOrderByNode] = set()
        self.where_function_nodes: set[SQLAlchemyQueryNode] = set()

    def _add_scope_id(self, name: str) -> str:
        return name if self.is_root else f"{name}_{self.level}"

    def _node_key(self, node: SQLAlchemyQueryNode) -> str:
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
    def referenced_function_nodes(self) -> set[SQLAlchemyQueryNode]:
        return (self.where_function_nodes & self.selection_function_nodes) | self.order_by_function_nodes

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def root_alias(self) -> AliasedClass[Any]:
        return self._root_alias

    def inspect(self, node: SQLAlchemyQueryNode) -> NodeInspect:
        return NodeInspect(node, self)

    def alias_from_relation_node(self, node: SQLAlchemyQueryNode, side: RelationshipSide) -> AliasedClass[Any]:
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

    def aliased_attribute(
        self, node: SQLAlchemyQueryNode, alias: AliasedClass[Any] | None = None
    ) -> QueryableAttribute[Any]:
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
            >>> node = SQLAlchemyQueryNode(...)  # Node with model field reference
            >>> scope = QueryScope(User)  # Query scope for User model
            >>> # Get attribute with explicit alias
            >>> attr = scope.aliased_attribute(node, aliased(User))
            >>> # Get attribute with inferred alias
            >>> attr = scope.aliased_attribute(node)
        """
        model_field: QueryableAttribute[RelationshipProperty[Any]] = node.value.model_field
        if alias is not None:
            return model_field.adapt_to_entity(inspect(alias))
        parent = node.non_computed_parent(strict=True)
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
        self, node: SQLAlchemyQueryNode, alias: AliasedClass[Any] | None = None
    ) -> list[QueryableAttribute[Any]]:
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

    def literal_column(self, from_name: str, column_name: str) -> Label[Any]:
        return literal_column(f'{from_name}."{column_name}"').label(self._add_scope_id(column_name))

    def set_relation_alias(
        self,
        node: SQLAlchemyQueryNode,
        side: RelationshipSide,
        alias: AliasedClass[Any],
    ) -> None:
        self._node_alias_map[(node, side)] = alias

    def id_field_definitions(
        self, model: type[DeclarativeBase]
    ) -> list[GraphQLFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        root = QueryNode.root_node(model)
        return [
            GraphQLFieldDefinition.from_field(self._inspector.field_definition(pk, DTOConfig(Purpose.READ)))
            for pk in self.aliased_id_attributes(root)
        ]

    def key(self, element: str | SQLAlchemyQueryNode) -> str:
        """Generates a unique key for a query element or node.

        The key is used to uniquely identify elements within the query scope, ensuring
        proper referencing and preventing naming conflicts. The key generation strategy
        differs based on the input type:

        - For SQLAlchemyQueryNode: Generates a scoped name based on the node's position
          in the query structure, incorporating parent relationships and function prefixes
        - For string elements: Creates a unique name by appending a counter to prevent
          collisions with identical names

        Args:
            element: The element to generate a key for. Can be either:
                - A SQLAlchemyQueryNode: A node in the query structure
                - A string: A literal element name

        Returns:
            str: A unique key string that identifies the element within the query scope.
                 The key is scoped to the current query level to maintain uniqueness
                 across nested scopes.

        Example:
            >>> scope = QueryScope(User)
            >>> node = SQLAlchemyQueryNode(...)
            >>> scope.key(node)  # Returns a unique key for the node
            >>> scope.key("column_name")  # Returns a unique key for the literal
        """
        if isinstance(element, QueryNode):
            scoped_name = self._node_key(element)
        else:
            scoped_name = f"{element}_{self._literal_name_counts[element]}"
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
        )

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.model},{self.level}>"
