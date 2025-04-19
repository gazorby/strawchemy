"""This module defines factories for creating GraphQL DTOs (Data Transfer Objects).

It includes factories for:
- Aggregate DTOs
- Aggregate Filter DTOs
- OrderBy DTOs
- Type DTOs
- Filter DTOs
- Enum DTOs

These factories are used to generate DTOs that are compatible with GraphQL schemas,
allowing for efficient data transfer and filtering in GraphQL queries.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import cached_property
from typing import TYPE_CHECKING, Any, TypeVar, override

from strawchemy.dto.base import DTOBase, DTOFactory, DTOFieldDefinition, ModelFieldT, ModelT, Relation
from strawchemy.graph import Node
from strawchemy.graphql import typing as strawchemy_typing
from strawchemy.graphql.dto import DTOKey, GraphQLFieldDefinition
from strawchemy.graphql.typing import GraphQLDTOT

if TYPE_CHECKING:
    from collections.abc import Generator

    from strawchemy.dto.types import DTOConfig
    from strawchemy.graph import Node
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol


__all__ = ("GraphQLDTOFactory",)

T = TypeVar("T")


class GraphQLDTOFactory(DTOFactory[ModelT, ModelFieldT, GraphQLDTOT]):
    inspector: GraphQLInspectorProtocol[Any, ModelFieldT]

    def type_description(self) -> str:
        return "GraphQL type"

    @cached_property
    def _namespace(self) -> dict[str, Any]:
        from strawchemy.sqlalchemy import hook

        return vars(strawchemy_typing) | vars(hook)

    @override
    def type_hint_namespace(self) -> dict[str, Any]:
        return super().type_hint_namespace() | self._namespace

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, GraphQLDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            key = DTOKey.from_dto_node(node)
            graphql_field = GraphQLFieldDefinition.from_field(field)
            yield graphql_field
            field_map[key + field.name] = graphql_field

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, GraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[GraphQLDTOT]:
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] = {}
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            field_map=field_map,
            **kwargs,
        )
        if not dto.__strawchemy_field_map__:
            dto.__strawchemy_field_map__ = field_map
        dto.__strawchemy_description__ = self.type_description()
        return dto
