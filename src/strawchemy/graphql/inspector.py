from __future__ import annotations

from typing import TYPE_CHECKING, Any

from strawchemy.dto import DTOFieldDefinition, ModelFieldT, ModelInspector, ModelT

if TYPE_CHECKING:
    from . import GraphQLFilter
    from .dto import GraphQLComparison

__all__ = ("GraphQLInspectorProtocol",)


class GraphQLInspectorProtocol(ModelInspector[ModelT, ModelFieldT]):
    """GraphQL inspector implementation."""

    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[ModelT, ModelFieldT]
    ) -> type[GraphQLFilter[ModelT, ModelFieldT]]: ...

    def get_type_comparison(self, type_: type[Any]) -> type[GraphQLComparison[ModelT, ModelFieldT]]: ...
