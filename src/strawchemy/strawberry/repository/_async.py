from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar, overload

from typing_extensions import TypeIs

from strawberry.types import get_object_definition, has_object_definition
from strawberry.types.lazy_type import LazyType
from strawberry.types.nodes import SelectedField, Selection
from strawchemy.exceptions import StrawchemyError
from strawchemy.graphql.constants import ORDER_BY_KEY
from strawchemy.graphql.dto import (
    BooleanFilterDTO,
    DTOKey,
    EnumDTO,
    OrderByDTO,
    QueryNode,
    RelationFilterDTO,
    StrawchemyDTOAttributes,
)
from strawchemy.sqlalchemy.repository import SQLAlchemyGraphQLAsyncRepository
from strawchemy.strawberry._utils import (
    default_session_getter,
    dto_model_from_type,
    pydantic_from_strawberry_type,
    strawberry_contained_type,
)
from strawchemy.utils import camel_to_snake, snake_keys

from ._node import _StrawberryQueryNode

if TYPE_CHECKING:
    from pydantic import BaseModel
    from sqlalchemy import Select
    from strawberry import Info
    from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
    from strawberry.types.field import StrawberryField
    from strawchemy.sqlalchemy.hook import QueryHook
    from strawchemy.sqlalchemy.typing import AnyAsyncSession
    from strawchemy.strawberry.typing import (
        AsyncSessionGetter,
        StrawchemyTypeFromPydantic,
        StrawchemyTypeWithStrawberryObjectDefinition,
    )

__all__ = ("StrawchemyAsyncRepository",)

T = TypeVar("T")


def _has_pydantic_type(type_: Any) -> TypeIs[type[StrawberryTypeFromPydantic[BaseModel]]]:
    return hasattr(type_, "_pydantic_type")


@dataclass
class StrawchemyAsyncRepository(Generic[T]):
    _ignored_field_names: ClassVar[frozenset[str]] = frozenset({"__typename"})

    root_type: type[T]
    info: Info[Any, Any]
    root_aggregations: bool = False
    auto_snake_case: bool = True

    # sqlalchemy related settings
    session_getter: AsyncSessionGetter = default_session_getter
    session: AnyAsyncSession | None = None
    filter_statement: Select[tuple[Any]] | None = None
    execution_options: dict[str, Any] | None = None

    _query_hooks: defaultdict[QueryNode[Any, Any], list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list), init=False
    )
    _tree: _StrawberryQueryNode[T] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        inner_root_type = strawberry_contained_type(self.root_type)
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

    def graphql_repository(self) -> SQLAlchemyGraphQLAsyncRepository[Any]:
        return SQLAlchemyGraphQLAsyncRepository(
            model=dto_model_from_type(strawberry_contained_type(self.root_type)),
            session=self.session or self.session_getter(self.info),
            statement=self.filter_statement,
            execution_options=self.execution_options,
        )

    @classmethod
    def _relation_filter(
        cls, selection: SelectedField, strawberry_field: StrawberryField, auto_snake_case: bool = True
    ) -> RelationFilterDTO[Any]:
        argument_types = {arg.python_name: arg.type for arg in strawberry_field.arguments}
        selection_arguments = snake_keys(selection.arguments) if auto_snake_case else selection.arguments
        if order_by_type := argument_types.get(ORDER_BY_KEY):
            order_by_model = pydantic_from_strawberry_type(strawberry_contained_type(order_by_type))
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
        strawberry_type = strawberry_contained_type(strawberry_type)
        if isinstance(strawberry_type, LazyType):
            strawberry_type = strawberry_type.resolve_type()
        strawberry_definition = get_object_definition(strawberry_type, strict=True)

        if strawberry_type.__strawchemy_query_hook__:
            self._add_query_hooks(strawberry_type.__strawchemy_query_hook__, node)

        for selection in selected_fields:
            if not isinstance(selection, SelectedField) or selection.name in self._ignored_field_names:
                continue
            model_field_name = camel_to_snake(selection.name) if self.auto_snake_case else selection.name
            strawberry_field = next(field for field in strawberry_definition.fields if field.name == model_field_name)
            strawberry_field_type = strawberry_contained_type(strawberry_field.type)
            dto_model = dto_model_from_type(strawberry_type)

            if (hooks := self._get_field_hooks(strawberry_field)) is not None:
                self._add_query_hooks(hooks, node)

            if _has_pydantic_type(strawberry_type):
                dto = pydantic_from_strawberry_type(strawberry_type)
            elif has_object_definition(strawberry_type):
                dto = strawberry_type
            else:
                msg = f"Unsupported type: {strawberry_type}"
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

    async def get_one_or_none(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> T | None:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        if result := query_results.one_or_none():
            return self._tree.to_strawberry_type(result)
        return None

    async def get_one(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> T:
        query_results = await self.graphql_repository().get_one(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        return self._tree.to_strawberry_type(query_results.one())

    @overload
    async def get_by_id(self, strict: Literal[True]) -> T: ...

    @overload
    async def get_by_id(self, strict: Literal[False]) -> T | None: ...

    @overload
    async def get_by_id(self, strict: bool = False) -> T | None: ...

    async def get_by_id(self, strict: bool = False, **kwargs: Any) -> T | None:
        query_results = await self.graphql_repository().get_by_id(
            selection=self._tree, query_hooks=self._query_hooks, **kwargs
        )
        result = query_results.one() if strict else query_results.one_or_none()
        return self._tree.to_strawberry_type(result) if result else None

    async def list(
        self,
        filter_input: StrawchemyTypeFromPydantic[BooleanFilterDTO[Any, Any]] | None = None,
        order_by: list[StrawchemyTypeFromPydantic[OrderByDTO[Any, Any]]] | None = None,
        distinct_on: list[EnumDTO] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[T] | T:
        query_results = await self.graphql_repository().list(
            selection=self._tree,
            dto_filter=filter_input.to_pydantic() if filter_input else None,
            order_by=[value.to_pydantic() for value in order_by or []],
            distinct_on=distinct_on,
            limit=limit,
            offset=offset,
            query_hooks=self._query_hooks,
        )
        if self.root_aggregations:
            return self._tree.aggregation_query_result_to_strawberry_type(query_results)
        return self._tree.query_result_to_strawberry_type(query_results)
