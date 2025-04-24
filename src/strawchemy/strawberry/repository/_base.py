from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from typing_extensions import TypeIs

from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.lazy_type import LazyType
from strawberry.types.nodes import FragmentSpread, InlineFragment, SelectedField, Selection
from strawchemy.exceptions import StrawchemyError
from strawchemy.graphql.constants import ORDER_BY_KEY
from strawchemy.graphql.dto import (
    DTOKey,
    QueryNode,
    RelationFilterDTO,
    StrawchemyDTOAttributes,
)
from strawchemy.strawberry._utils import (
    dto_model_from_type,
    pydantic_from_strawberry_type,
    strawberry_contained_user_type,
)
from strawchemy.strawberry.types import error_type_names
from strawchemy.utils import camel_to_snake, snake_keys

from ._node import _StrawberryQueryNode

if TYPE_CHECKING:
    from pydantic import BaseModel

    from strawberry import Info
    from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
    from strawberry.types.field import StrawberryField
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.strawberry.typing import (
        StrawchemyTypeWithStrawberryObjectDefinition,
    )

__all__ = ("StrawchemyRepository",)

T = TypeVar("T")


def _has_pydantic_type(type_: Any) -> TypeIs[type[StrawberryTypeFromPydantic[BaseModel]]]:
    return hasattr(type_, "_pydantic_type")


@dataclass
class StrawchemyRepository(Generic[T]):
    _ignored_field_names: ClassVar[frozenset[str]] = frozenset({"__typename"})

    type: type[T]
    info: Info[Any, Any]
    root_aggregations: bool = False
    auto_snake_case: bool = True

    _query_hooks: defaultdict[QueryNode[Any, Any], list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list), init=False
    )
    _tree: _StrawberryQueryNode[T] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        inner_root_type = strawberry_contained_user_type(self.type)
        resolver_selection = next(
            selection
            for selection in self.info.selected_fields
            if isinstance(selection, SelectedField) and selection.name == self.info.field_name
        )
        node = _StrawberryQueryNode.root_node(
            dto_model_from_type(inner_root_type),
            strawberry_type=inner_root_type,
            root_aggregations=self.root_aggregations,
        )

        self._build(inner_root_type, resolver_selection.selections, node)
        self._tree = node.merge_same_children(match_on="value_equality")

    @classmethod
    def _relation_filter(
        cls, selection: SelectedField, strawberry_field: StrawberryField, auto_snake_case: bool = True
    ) -> RelationFilterDTO[Any]:
        argument_types = {arg.python_name: arg.type for arg in strawberry_field.arguments}
        selection_arguments = snake_keys(selection.arguments) if auto_snake_case else selection.arguments
        if order_by_type := argument_types.get(ORDER_BY_KEY):
            order_by_model = pydantic_from_strawberry_type(strawberry_contained_user_type(order_by_type))
            return RelationFilterDTO[order_by_model].model_validate(selection_arguments)
        return RelationFilterDTO.model_validate(selection_arguments)

    @classmethod
    def _get_field_hooks(cls, field: StrawberryField) -> QueryHook[Any] | Sequence[QueryHook[Any]] | None:
        from strawchemy.strawberry import StrawchemyField

        return field.query_hook if isinstance(field, StrawchemyField) else None

    def _add_query_hooks(
        self, query_hooks: QueryHook[Any] | Sequence[QueryHook[Any]], node: _StrawberryQueryNode[Any]
    ) -> None:
        hooks = query_hooks if isinstance(query_hooks, Collection) else [query_hooks]
        for hook in hooks:
            hook.info_var.set(self.info)
            self._query_hooks[node].append(hook)

    def _build(
        self,
        strawberry_type: type[StrawchemyTypeWithStrawberryObjectDefinition],
        selected_fields: list[Selection],
        node: _StrawberryQueryNode[Any],
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

            if _has_pydantic_type(selection_type):
                dto = pydantic_from_strawberry_type(selection_type)
            elif has_object_definition(selection_type):
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

            child_node = _StrawberryQueryNode(
                value=field_definition,
                strawberry_type=strawberry_field_type,
                relation_filter=self._relation_filter(selection, strawberry_field),
            )
            child = node.insert_node(child_node)
            if selection.selections:
                self._build(strawberry_field_type, selection.selections, child)
