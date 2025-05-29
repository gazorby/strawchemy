from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar, overload

from msgspec import convert

from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.lazy_type import LazyType
from strawberry.types.nodes import FragmentSpread, InlineFragment, SelectedField, Selection
from strawchemy.constants import JSON_PATH_KEY, ORDER_BY_KEY
from strawchemy.dto.base import ModelT
from strawchemy.exceptions import StrawchemyError
from strawchemy.graph import NodeMetadata
from strawchemy.strawberry._utils import dto_model_from_type, strawberry_contained_user_type
from strawchemy.strawberry.dto import (
    DTOKey,
    OrderByRelationFilterDTO,
    QueryNode,
    QueryNodeMetadata,
    RelationFilterDTO,
    StrawchemyDTOAttributes,
)
from strawchemy.strawberry.mutation.types import error_type_names
from strawchemy.utils import camel_to_snake, snake_keys

from ._node import StrawberryQueryNode

if TYPE_CHECKING:
    from strawberry import Info
    from strawberry.types.field import StrawberryField
    from strawchemy.sqlalchemy._executor import QueryResult
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.strawberry.typing import QueryNodeType, StrawchemyTypeWithStrawberryObjectDefinition

__all__ = ("GraphQLResult", "StrawchemyRepository")

T = TypeVar("T")


@dataclass
class GraphQLResult(Generic[ModelT, T]):
    query_result: QueryResult[ModelT]
    tree: StrawberryQueryNode[T]

    def graphql_type(self) -> T:
        return self.tree.node_result_to_strawberry_type(self.query_result.one())

    def graphql_type_or_none(self) -> T | None:
        node_result = self.query_result.one_or_none()
        return self.tree.node_result_to_strawberry_type(node_result) if node_result else None

    @overload
    def graphql_list(self, root_aggregations: Literal[False]) -> list[T]: ...

    @overload
    def graphql_list(self, root_aggregations: Literal[True]) -> T: ...

    @overload
    def graphql_list(self) -> list[T]: ...

    def graphql_list(self, root_aggregations: bool = False) -> list[T] | T:
        if root_aggregations:
            return self.tree.aggregation_query_result_to_strawberry_type(self.query_result)
        return [self.tree.node_result_to_strawberry_type(node_result) for node_result in self.query_result]

    @property
    def instances(self) -> Sequence[ModelT]:
        return self.query_result.nodes

    @property
    def instance(self) -> ModelT:
        return self.query_result.one().model


@dataclass
class StrawchemyRepository(Generic[T]):
    _ignored_field_names: ClassVar[frozenset[str]] = frozenset({"__typename"})

    type: type[T]
    info: Info[Any, Any]
    root_aggregations: bool = False
    auto_snake_case: bool = True

    _query_hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list), init=False
    )
    _tree: StrawberryQueryNode[T] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        inner_root_type = strawberry_contained_user_type(self.type)
        resolver_selection = next(
            selection
            for selection in self.info.selected_fields
            if isinstance(selection, SelectedField) and selection.name == self.info.field_name
        )
        node = StrawberryQueryNode.root_node(
            dto_model_from_type(inner_root_type),
            strawberry_type=inner_root_type,
            root_aggregations=self.root_aggregations,
        )

        self._build(inner_root_type, resolver_selection.selections, node)
        self._tree = node.merge_same_children(match_on="value_equality")

    def _relation_filter(
        self, selection: SelectedField, strawberry_field: StrawberryField, arguments: dict[str, Any]
    ) -> RelationFilterDTO:
        argument_types = {arg.python_name: arg.type for arg in strawberry_field.arguments}
        if order_by_args := arguments.get(ORDER_BY_KEY):
            if not isinstance(order_by_args, list):
                arguments[ORDER_BY_KEY] = [arguments[ORDER_BY_KEY]]
            order_by_model = strawberry_contained_user_type(argument_types[ORDER_BY_KEY])
            return convert(arguments, type=OrderByRelationFilterDTO[order_by_model], strict=False)
        return convert(arguments, type=RelationFilterDTO, strict=False)

    @classmethod
    def _get_field_hooks(cls, field: StrawberryField) -> QueryHook[Any] | Sequence[QueryHook[Any]] | None:
        from strawchemy.strawberry._field import StrawchemyField

        return field.query_hook if isinstance(field, StrawchemyField) else None

    def _add_query_hooks(self, query_hooks: QueryHook[Any] | Sequence[QueryHook[Any]], node: QueryNodeType) -> None:
        hooks = query_hooks if isinstance(query_hooks, Collection) else [query_hooks]
        for hook in hooks:
            hook.info_var.set(self.info)
            self._query_hooks[node].append(hook)

    def _build(
        self,
        strawberry_type: type[StrawchemyTypeWithStrawberryObjectDefinition],
        selected_fields: list[Selection],
        node: QueryNodeType,
    ) -> None:
        selection_type = strawberry_contained_user_type(strawberry_type)
        if isinstance(selection_type, LazyType):
            selection_type = selection_type.resolve_type()
        strawberry_definition = get_object_definition(selection_type, strict=True)

        if selection_type.__strawchemy_query_hook__:
            self._add_query_hooks(selection_type.__strawchemy_query_hook__, node)

        for selection in selected_fields:
            if (
                isinstance(selection, FragmentSpread | InlineFragment)
                and selection.type_condition not in error_type_names()
            ):
                self._build(strawberry_type, selection.selections, node)
                continue
            if not isinstance(selection, SelectedField) or selection.name in self._ignored_field_names:
                continue

            model_field_name = camel_to_snake(selection.name) if self.auto_snake_case else selection.name
            strawberry_field = next(field for field in strawberry_definition.fields if field.name == model_field_name)
            strawberry_field_type = strawberry_contained_user_type(strawberry_field.type)
            dto_model = dto_model_from_type(selection_type)

            if (hooks := self._get_field_hooks(strawberry_field)) is not None:
                self._add_query_hooks(hooks, node)

            if has_object_definition(selection_type):
                dto = selection_type
            else:
                msg = f"Unsupported type: {selection_type}"
                raise StrawchemyError(msg)
            assert issubclass(dto, StrawchemyDTOAttributes)

            key = DTOKey.from_query_node(QueryNode.root_node(dto_model)) + strawberry_field.name

            try:
                field_definition = dto.__strawchemy_field_map__[key]
            except KeyError:
                continue

            selection_arguments = snake_keys(selection.arguments) if self.auto_snake_case else selection.arguments

            child_node = StrawberryQueryNode(
                value=field_definition,
                node_metadata=NodeMetadata(
                    QueryNodeMetadata(
                        relation_filter=self._relation_filter(selection, strawberry_field, selection_arguments),
                        strawberry_type=strawberry_field_type,
                        json_path=selection_arguments.get(JSON_PATH_KEY),
                    )
                ),
            )
            child = node.insert_node(child_node)
            if selection.selections:
                self._build(strawberry_field_type, selection.selections, child)
