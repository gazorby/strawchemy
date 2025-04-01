from __future__ import annotations

import dataclasses
from collections.abc import Generator
from typing import TYPE_CHECKING, Any, TypeVar, override

from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.base import (
    DTOBackend,
    DTOBase,
    DTOFactory,
    DTOFieldDefinition,
    ModelFieldT,
    ModelT,
    Relation,
)
from strawchemy.dto.types import DTO_MISSING, DTOConfig, Purpose
from strawchemy.graph import Node
from strawchemy.graphql import typing as strawchemy_typing
from strawchemy.graphql.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.graphql.dto import (
    AggregateDTO,
    AggregateFieldDefinition,
    DTOKey,
    EnumDTO,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
)
from strawchemy.graphql.typing import AggregateDTOT, GraphQLDTOT

from .aggregations import AggregationInspector
from .enum import EnumDTOFactory

if TYPE_CHECKING:
    from collections.abc import Generator

    from strawchemy.graph import Node
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol


__all__ = ("AggregateDTOFactory", "DistinctOnFieldsDTOFactory", "RootAggregateTypeDTOFactory", "TypeDTOFactory")

T = TypeVar("T")

_TYPING_NS = vars(strawchemy_typing)


class GraphQLDTOFactory(DTOFactory[ModelT, ModelFieldT, GraphQLDTOT]):
    inspector: GraphQLInspectorProtocol[Any, ModelFieldT]

    def type_description(self) -> str:
        return "GraphQL type"

    @override
    def type_hint_namespace(self) -> dict[str, Any]:
        return super().type_hint_namespace() | _TYPING_NS

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


class TypeDTOFactory(GraphQLDTOFactory[ModelT, ModelFieldT, GraphQLDTOT]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[GraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_factory: AggregateDTOFactory[ModelT, ModelFieldT, AggregateDTOT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inspector, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_factory = aggregation_factory or AggregateDTOFactory(
            inspector, DataclassDTOBackend(AggregateDTO)
        )

    def _aggregation_field(
        self, field_def: DTOFieldDefinition[ModelT, ModelFieldT], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition[ModelT, ModelFieldT]:
        related_model = self.inspector.relation_model(field_def.model_field)
        aggregate_dto_config = dataclasses.replace(dto_config, annotation_overrides={})
        dto = self._aggregation_factory.factory(
            model=related_model, dto_config=aggregate_dto_config, parent_field_def=field_def
        )
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=dto.__dto_model__,  # pyright: ignore[reportGeneralTypeIssues]
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=dto,
            related_dto=dto,
        )

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, GraphQLDTOT], None] | None = None
    ) -> str:
        return f"{base_name}{'Input' if dto_config.purpose is Purpose.WRITE else ''}Type"

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
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            key = DTOKey.from_dto_node(node)
            if field.is_relation and field.uselist and aggregations:
                aggregation_field = self._aggregation_field(field, dto_config)
                field_map[key + aggregation_field.name] = aggregation_field
                yield aggregation_field
            yield field

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
        *,
        aggregations: bool = True,
        **kwargs: Any,
    ) -> type[GraphQLDTOT]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            aggregations=aggregations if dto_config.purpose is Purpose.READ else False,
            **kwargs,
        )


class RootAggregateTypeDTOFactory(TypeDTOFactory[ModelT, ModelFieldT, GraphQLDTOT]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[GraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        type_factory: TypeDTOFactory[ModelT, ModelFieldT, GraphQLDTOT] | None = None,
        aggregation_factory: AggregateDTOFactory[ModelT, ModelFieldT, AggregateDTOT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inspector, backend, handle_cycles, type_map, **kwargs)
        self._type_factory = type_factory or TypeDTOFactory(inspector, backend)
        self._aggregation_factory = aggregation_factory or AggregateDTOFactory(
            inspector, DataclassDTOBackend(AggregateDTO)
        )

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, GraphQLDTOT], None] | None = None
    ) -> str:
        return f"{base_name}Root"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, GraphQLDTOT], None],
        raise_if_no_fields: bool = False,
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[Any, ModelFieldT], None, None]:
        if not node.is_root:
            yield from ()
        key = DTOKey.from_dto_node(node)
        field_map = field_map if field_map is not None else {}
        nodes_dto = self._type_factory.factory(model, dto_config=dto_config, aggregations=aggregations)
        nodes = GraphQLFieldDefinition(
            dto_config=dto_config,
            model=model,
            model_field_name=NODES_KEY,
            type_hint=list[nodes_dto],
            is_relation=False,
        )
        aggregations_field = GraphQLFieldDefinition(
            dto_config=dto_config,
            model=model,
            model_field_name=AGGREGATIONS_KEY,
            type_hint=self._aggregation_factory.factory(model, dto_config=dto_config),
            is_relation=False,
            is_aggregate=True,
        )
        field_map[key + nodes.name] = nodes
        field_map[key + aggregations_field.name] = aggregations_field
        yield from iter((nodes, aggregations_field))

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
        *,
        aggregations: bool = True,
        **kwargs: Any,
    ) -> type[GraphQLDTOT]:
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            aggregations=aggregations,
            **kwargs,
        )
        dto.__strawchemy_is_root_aggregation_type__ = True
        return dto


class AggregateDTOFactory(GraphQLDTOFactory[ModelT, ModelFieldT, AggregateDTOT]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[AggregateDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_builder: AggregationInspector[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inspector, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_builder = aggregation_builder or AggregationInspector(inspector)

    @override
    def type_description(self) -> str:
        return "Aggregation fields"

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, AggregateDTOT], None] | None = None
    ) -> str:
        return f"{base_name}Aggregate"

    @override
    def _factory(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateDTOT], None],
        base: type[Any] | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> type[AggregateDTOT]:
        field_map = field_map if field_map is not None else {}
        model_field = parent_field_def.model_field if parent_field_def else None
        as_partial_config = dataclasses.replace(dto_config, partial=True)
        field_definitions: list[FunctionFieldDefinition[T, ModelFieldT]] = [
            FunctionFieldDefinition[T, ModelFieldT](
                dto_config=dto_config,
                model=model,
                _model_field=model_field if model_field is not None else DTO_MISSING,
                model_field_name=aggregation.function,
                type_hint=aggregation.output_type,
                _function=aggregation,
                default=aggregation.default,
            )
            for aggregation in self._aggregation_builder.output_functions(model, as_partial_config)
        ]

        root_key = DTOKey.from_dto_node(node)
        field_map.update({root_key + field.model_field_name: field for field in field_definitions})
        return self.backend.build(name, model, field_definitions, **(backend_kwargs or {}))


class DistinctOnFieldsDTOFactory(EnumDTOFactory[ModelT, ModelFieldT]):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}DistinctOnFields"
