from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.dto import DTOFieldDefinition, ModelInspector

if TYPE_CHECKING:
    from strawchemy.config.databases import DatabaseFeatures

    from . import GraphQLFilter
    from .dto import GraphQLComparison

__all__ = ("GraphQLInspectorProtocol",)


class GraphQLInspectorProtocol(ModelInspector[DeclarativeBase, QueryableAttribute[Any]]):
    """GraphQL inspector implementation."""

    db_features: DatabaseFeatures

    def get_field_comparison(
        self, field_definition: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]
    ) -> type[GraphQLFilter]: ...

    def get_type_comparison(self, type_: type[Any]) -> type[GraphQLComparison]: ...
