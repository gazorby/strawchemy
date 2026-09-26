"""Base strawberry module for Strawchemy framework.

This module provides the core strawberry implementation for GraphQL data access
in Strawchemy, including base classes for query building and result handling.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar, cast, overload

from graphql import (
    FragmentSpreadNode,
    GraphQLIncludeDirective,
    GraphQLSkipDirective,
    GraphQLUnionType,
    InlineFragmentNode,
    assert_composite_type,
    get_argument_values,
    get_directive_values,
    get_named_type,
)
from graphql.execution import values as graphql_values
from msgspec import convert
from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.enum import StrawberryEnumDefinition
from strawberry.types.lazy_type import LazyType

from strawchemy.constants import DISTINCT_ON_KEY, JSON_PATH_KEY, ORDER_BY_KEY
from strawchemy.dto.base import ModelT
from strawchemy.dto.strawberry import QueryNodeMetadata, RelationFilterDTO, StrawchemyObject
from strawchemy.exceptions import StrawchemyError
from strawchemy.repository.strawberry._node import StrawberryQueryNode
from strawchemy.schema.mutation import error_type_names
from strawchemy.transpiler import QueryHook
from strawchemy.utils.graph import NodeMetadata
from strawchemy.utils.strawberry import dto_model_from_type, strawberry_contained_user_type
from strawchemy.utils.text import camel_to_snake, snake_keys

if TYPE_CHECKING:
    from collections.abc import Sequence

    from graphql import FieldNode, GraphQLCompositeType, GraphQLField, GraphQLResolveInfo, GraphQLType, SelectionNode
    from strawberry import Info
    from strawberry.types.field import StrawberryField

    from strawchemy.transpiler import QueryResult
    from strawchemy.typing import QueryNodeType, StrawchemyObjectWithStrawberryObjectDefinition

__all__ = ("IS_ASYNC_REPOSITORY", "IS_SYNC_REPOSITORY", "GraphQLResult", "StrawchemyRepository")

T = TypeVar("T")

# graphql-core 3.3 coerces from a `VariableValues`, which strawberry unwraps into its coerced dict on `Info`.
_VariableValues: Any = getattr(graphql_values, "VariableValues", None)

IS_ASYNC_REPOSITORY: bool = True
IS_SYNC_REPOSITORY: bool = not IS_ASYNC_REPOSITORY


@dataclass
class GraphQLResult(Generic[ModelT, T]):
    """Container for GraphQL query results with conversion utilities.

    This class provides methods to convert raw query results into their corresponding
    GraphQL types, handling both single results and collections.

    Attributes:
        query_result: The raw query result from the database
        tree: The query tree used to construct the result
    """

    query_result: QueryResult[ModelT]
    tree: StrawberryQueryNode[T]

    def graphql_type(self) -> T:
        """Convert the query result to a single GraphQL type.

        Returns:
            A single instance of the GraphQL type

        Raises:
            NoResultFound: If no result is found
            MultipleResultsFound: If multiple results are found
        """
        return self.tree.node_result_to_strawberry_type(self.query_result.one())

    def graphql_type_or_none(self) -> T | None:
        """Convert the query result to a single GraphQL type or None.

        Returns:
            A single instance of the GraphQL type, or None if no result is found
        """
        node_result = self.query_result.one_or_none()
        return self.tree.node_result_to_strawberry_type(node_result) if node_result else None

    @overload
    def graphql_list(self, root_aggregations: Literal[False]) -> list[T]: ...

    @overload
    def graphql_list(self, root_aggregations: Literal[True]) -> T: ...

    @overload
    def graphql_list(self) -> list[T]: ...

    def graphql_list(self, root_aggregations: bool = False) -> list[T] | T:
        """Convert the query result to a list of GraphQL types or aggregated result.

        Args:
            root_aggregations: If True, returns aggregated results as a single object.
                             If False, returns a list of individual results.

        Returns:
            Either a list of GraphQL types or a single aggregated result object,
            depending on the root_aggregations flag
        """
        if root_aggregations:
            return self.tree.aggregation_query_result_to_strawberry_type(self.query_result)
        return [self.tree.node_result_to_strawberry_type(node_result) for node_result in self.query_result]

    @property
    def instances(self) -> Sequence[ModelT]:
        """Get the raw model instances from the query result.

        Returns:
            A sequence of raw model instances
        """
        return self.query_result.nodes

    @property
    def instance(self) -> ModelT:
        """Get a single raw model instance from the query result.

        Returns:
            A single model instance

        Raises:
            NoResultFound: If no result is found
            MultipleResultsFound: If multiple results are found
        """
        return self.query_result.one().model


@dataclass
class StrawchemyRepository(Generic[T]):
    """Base strawberry for GraphQL data access in Strawchemy.

    This class provides the core functionality for building and executing GraphQL queries
    against a database, with support for filtering, ordering, and field selection.

    Args:
        type: The Strawberry GraphQL type this strawberry works with
        info: The GraphQL resolver info object
        root_aggregations: Whether to enable root-level aggregations
        auto_snake_case: Whether to automatically convert field names to snake_case
        query_hook: Hooks applied to the root node, as a type-level hook would be

    Attributes:
        _ignored_field_names: Set of field names to ignore during query building
        _query_hooks: Dictionary of query hooks registered for different query nodes
        _tree: The query tree built from the GraphQL selection
    """

    _ignored_field_names: ClassVar[frozenset[str]] = frozenset({"__typename"})

    is_async: ClassVar[bool]

    type: type[T]
    info: Info[Any, Any]
    root_aggregations: bool = False
    auto_snake_case: bool = True
    query_hook: QueryHook[Any] | Sequence[QueryHook[Any]] | None = None

    _query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list), init=False
    )
    _tree: StrawberryQueryNode[T] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        inner_root_type = strawberry_contained_user_type(self.type)
        root_selections = [
            selection
            for field_node in self._raw_info.field_nodes
            if field_node.selection_set
            for selection in field_node.selection_set.selections
        ]
        node = StrawberryQueryNode.root_node(
            dto_model_from_type(inner_root_type),
            strawberry_type=inner_root_type,
            root_aggregations=self.root_aggregations,
        )
        root_field = self._raw_info.field_nodes[0]
        node.metadata.data.response_keys = ((root_field.alias or root_field.name).value,)

        if self.query_hook is not None:
            self._add_query_hooks(self.query_hook, node)
        self._build(inner_root_type, _composite_type(self._raw_info.return_type), root_selections, node)
        self._tree = node

    @property
    def _raw_info(self) -> GraphQLResolveInfo:
        return self.info._raw_info  # noqa: SLF001

    @cached_property
    def _variable_values(self) -> Any:
        variable_values = self._raw_info.variable_values
        return variable_values if _VariableValues is None else _VariableValues({}, variable_values)

    def _fragment_selection(
        self, selection: FragmentSpreadNode | InlineFragmentNode, graphql_type: GraphQLCompositeType
    ) -> tuple[GraphQLCompositeType, Sequence[SelectionNode]]:
        fragment = (
            self._raw_info.fragments[selection.name.value] if isinstance(selection, FragmentSpreadNode) else selection
        )
        if fragment.type_condition is not None:
            graphql_type = _composite_type(self._raw_info.schema.get_type(fragment.type_condition.name.value))
        return graphql_type, fragment.selection_set.selections

    def _is_included(self, selection: SelectionNode) -> bool:
        variable_values = self._variable_values
        skip = get_directive_values(GraphQLSkipDirective, selection, variable_values)
        include = get_directive_values(GraphQLIncludeDirective, selection, variable_values)
        return not (skip and skip["if"]) and not (include and not include["if"])

    def _relation_filter(
        self, strawberry_field: StrawberryField, arguments: dict[str, Any]
    ) -> RelationFilterDTO[Any, Any]:
        argument_types = {arg.python_name: arg.type for arg in strawberry_field.arguments}
        arguments = {name: value for name, value in arguments.items() if value is not None}
        for key in (ORDER_BY_KEY, DISTINCT_ON_KEY):
            if key in arguments and not isinstance(arguments[key], list):
                arguments[key] = [arguments[key]]
        order_by_type = self._argument_item_type(argument_types, ORDER_BY_KEY)
        distinct_on_type = self._argument_item_type(argument_types, DISTINCT_ON_KEY)
        return convert(arguments, type=RelationFilterDTO[order_by_type, distinct_on_type], strict=False)

    def _selection_arguments(self, selection: FieldNode, graphql_field: GraphQLField) -> dict[str, Any]:
        arguments = get_argument_values(graphql_field, selection, self._variable_values)
        return snake_keys(arguments) if self.auto_snake_case else arguments

    @staticmethod
    def _argument_item_type(argument_types: dict[str, Any], name: str) -> Any:
        if name not in argument_types:
            return Any
        item_type = strawberry_contained_user_type(argument_types[name])
        return item_type.wrapped_cls if isinstance(item_type, StrawberryEnumDefinition) else item_type

    @classmethod
    def _get_field_hooks(cls, field: StrawberryField) -> QueryHook[Any] | Sequence[QueryHook[Any]]:
        from strawchemy.schema.field import StrawchemyField  # noqa: PLC0415

        hooks = field.query_hook if isinstance(field, StrawchemyField) else None
        return () if hooks is None else hooks

    def _add_query_hooks(self, query_hooks: QueryHook[Any] | Sequence[QueryHook[Any]], node: QueryNodeType) -> None:
        node_hooks = self._query_hooks[node]
        for hook in [query_hooks] if isinstance(query_hooks, QueryHook) else query_hooks:
            if any(existing is hook for existing in node_hooks):
                continue
            hook.info_var.set(self.info)
            node_hooks.append(hook)

    @staticmethod
    def _upsert_child(node: QueryNodeType, child: QueryNodeType) -> QueryNodeType:
        return next(
            (
                existing
                for existing in node.children
                if existing.value == child.value and existing.metadata.data.arguments == child.metadata.data.arguments
            ),
            None,
        ) or node.insert_node(child)

    def _build(
        self,
        strawberry_type: type[StrawchemyObjectWithStrawberryObjectDefinition],
        graphql_type: GraphQLCompositeType,
        selections: Sequence[SelectionNode],
        node: QueryNodeType,
    ) -> None:
        selection_type = strawberry_contained_user_type(strawberry_type)
        if isinstance(selection_type, LazyType):
            selection_type = selection_type.resolve_type()
        strawberry_definition = get_object_definition(selection_type, strict=True)

        self._add_query_hooks(selection_type.__strawchemy_definition__.query_hooks, node)

        for selection in cast("Sequence[FieldNode | FragmentSpreadNode | InlineFragmentNode]", selections):
            if not self._is_included(selection):
                continue
            if isinstance(selection, (FragmentSpreadNode, InlineFragmentNode)):
                fragment_type, fragment_selections = self._fragment_selection(selection, graphql_type)
                if fragment_type.name not in error_type_names():
                    self._build(strawberry_type, fragment_type, fragment_selections, node)
                continue
            if selection.name.value in self._ignored_field_names:
                continue

            model_field_name = camel_to_snake(selection.name.value) if self.auto_snake_case else selection.name.value
            strawberry_field = next(field for field in strawberry_definition.fields if field.name == model_field_name)
            strawberry_field_type = strawberry_contained_user_type(strawberry_field.type)

            if has_object_definition(selection_type):
                dto = selection_type
            else:
                msg = f"Unsupported type: {selection_type}"
                raise StrawchemyError(msg)
            assert issubclass(dto, StrawchemyObject)

            field_definition = dto.__dto_field_definitions__.get(strawberry_field.name)
            hooks = self._get_field_hooks(strawberry_field)
            if field_definition is None:
                self._add_query_hooks(hooks, node)
                continue

            assert not isinstance(graphql_type, GraphQLUnionType)
            graphql_field = graphql_type.fields[selection.name.value]
            selection_arguments = self._selection_arguments(selection, graphql_field)

            child_node = StrawberryQueryNode(
                value=field_definition,
                node_metadata=NodeMetadata(
                    QueryNodeMetadata(
                        relation_filter=self._relation_filter(strawberry_field, selection_arguments),
                        strawberry_type=strawberry_field_type,
                        json_path=selection_arguments.get(JSON_PATH_KEY),
                    )
                ),
            )
            child = self._upsert_child(node, child_node)
            child.metadata.data.response_keys += ((selection.alias or selection.name).value,)
            # A relation field's hook targets the related model; a column or resolver field's hook the owning one.
            is_relation_field = field_definition.is_relation and strawberry_field.base_resolver is None
            self._add_query_hooks(hooks, child if is_relation_field else node)
            if selection.selection_set:
                self._build(
                    strawberry_field_type,
                    _composite_type(graphql_field.type),
                    selection.selection_set.selections,
                    child,
                )


def _composite_type(graphql_type: GraphQLType | None) -> GraphQLCompositeType:
    return cast("GraphQLCompositeType", assert_composite_type(get_named_type(graphql_type)))
