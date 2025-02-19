from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from strawchemy.dto import DTOConfig, DTOFieldDefinition, ModelFieldT, ModelT
from strawchemy.graphql.dto import OrderByEnum
from strawchemy.graphql.filters import DateComparison, GraphQLComparison, GraphQLFilter, TimeComparison
from strawchemy.graphql.inspector import GraphQLInspectorProtocol

from ._utils import pydantic_from_strawberry_type

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .factory import StrawberryRegistry

__all__ = ("_StrawberryModelInspector",)


class _StrawberryModelInspector(GraphQLInspectorProtocol[ModelT, ModelFieldT]):
    def __init__(self, inspector: GraphQLInspectorProtocol[ModelT, ModelFieldT], registry: StrawberryRegistry) -> None:
        self._inspector = inspector
        self._registry = registry

    def _register_sub_types(self, comparison_type: type[GraphQLFilter[ModelT, ModelFieldT]]) -> None:
        if issubclass(comparison_type, TimeComparison | DateComparison):
            self._registry.register_comparison_type(self._inspector.get_type_comparison(int))

    @override
    def field_definitions(
        self, model: type[Any], dto_config: DTOConfig
    ) -> Iterable[tuple[str, DTOFieldDefinition[ModelT, ModelFieldT]]]:
        return self._inspector.field_definitions(model, dto_config)

    @override
    def id_field_definitions(
        self, model: type[Any], dto_config: DTOConfig
    ) -> Iterable[tuple[str, DTOFieldDefinition[ModelT, ModelFieldT]]]:
        return self._inspector.id_field_definitions(model, dto_config)

    @override
    def field_definition(
        self, model_field: ModelFieldT, dto_config: DTOConfig
    ) -> DTOFieldDefinition[ModelT, ModelFieldT]:
        return self._inspector.field_definition(model_field, dto_config)

    @override
    def get_type_hints(self, type_: type[Any], include_extras: bool = True) -> dict[str, Any]:
        return self._inspector.get_type_hints(type_, include_extras)

    @override
    def relation_model(self, model_field: ModelFieldT) -> type[Any]:
        return self._inspector.relation_model(model_field)

    @override
    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[ModelT, ModelFieldT]
    ) -> type[GraphQLFilter[ModelT, ModelFieldT]]:
        comparison_type = self._inspector.get_field_comparison(field_definition)
        self._register_sub_types(comparison_type)
        if issubclass(comparison_type, OrderByEnum):
            return self._registry.register_enum(comparison_type, name="OrderByEnum")
        return pydantic_from_strawberry_type(self._registry.register_comparison_type(comparison_type))

    @override
    def get_type_comparison(self, type_: type[Any]) -> type[GraphQLComparison[ModelT, ModelFieldT]]:
        comparison_type = self._inspector.get_type_comparison(type_)
        self._register_sub_types(comparison_type)
        return pydantic_from_strawberry_type(self._registry.register_comparison_type(comparison_type))

    @override
    def model_field_type(self, field_definition: DTOFieldDefinition[ModelT, ModelFieldT]) -> Any:
        return self._inspector.model_field_type(field_definition)
