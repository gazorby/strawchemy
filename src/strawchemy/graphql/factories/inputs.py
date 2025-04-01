from __future__ import annotations

import dataclasses
from collections.abc import Generator
from typing import TYPE_CHECKING, Any, TypeVar, override

from strawchemy.dto.backend.pydantic import PydanticDTOBackend
from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelFieldT, ModelT, Relation
from strawchemy.dto.types import DTO_MISSING, DTOConfig, DTOMissingType, Purpose
from strawchemy.graph import Node
from strawchemy.graphql.dto import (
    AggregateFieldDefinition,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    DTOKey,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
)
from strawchemy.graphql.inspector import GraphQLInspectorProtocol
from strawchemy.graphql.typing import AggregateDTOT, AggregationFunction, GraphQLFilterDTOT
from strawchemy.utils import snake_to_camel

from .aggregations import AggregationInspector
from .base import GraphQLDTOFactory

if TYPE_CHECKING:
    from collections.abc import Generator

    from strawchemy.graph import Node
    from strawchemy.graphql.filters import GraphQLFilter, OrderComparison
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol


T = TypeVar("T")


class FilterDTOFactory(GraphQLDTOFactory[ModelT, ModelFieldT, GraphQLFilterDTOT]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[GraphQLFilterDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterDTOFactory[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inspector, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_filter_factory = aggregation_filter_factory or AggregateFilterDTOFactory(inspector)

    def _filter_type(self, field: DTOFieldDefinition[ModelT, ModelFieldT]) -> type[GraphQLFilter[ModelT, ModelFieldT]]:
        return self.inspector.get_field_comparison(field)

    def _aggregation_field(
        self,
        field_def: DTOFieldDefinition[ModelT, ModelFieldT],
        dto_config: DTOConfig,
    ) -> GraphQLFieldDefinition[ModelT, ModelFieldT]:
        related_model = self.inspector.relation_model(field_def.model_field)
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=related_model,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=self._aggregation_filter_factory.factory(
                model=related_model, dto_config=dto_config, parent_field_def=field_def
            ),
        )

    @override
    def type_description(self) -> str:
        return "Boolean expression to compare fields. All fields are combined with logical 'AND'."

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, GraphQLFilterDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        aggregate_filters: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            key = DTOKey.from_dto_node(node)
            if field.is_relation:
                field.type_ = field.type_ | None
                if field.uselist and field.related_dto:
                    field.type_ = field.related_dto | None
                if aggregate_filters:
                    aggregation_field = self._aggregation_field(field, dto_config)
                    field_map[key + aggregation_field.name] = aggregation_field
                    yield aggregation_field
            else:
                comparison_type = self._filter_type(field)
                field.type_ = comparison_type | None

            field.default = None
            field.default_factory = DTO_MISSING
            yield field

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, GraphQLFilterDTOT], None] | None = None
    ) -> str:
        return f"{base_name}BoolExp"

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, GraphQLFilterDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[GraphQLFilterDTOT]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            aggregate_filters=aggregate_filters,
            **kwargs,
        )


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


class AggregateFilterDTOFactory(GraphQLDTOFactory[ModelT, ModelFieldT, AggregateFilterDTO[ModelT]]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[AggregateFilterDTO[ModelT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_builder: AggregationInspector[Any, ModelFieldT] | None = None,
    ) -> None:
        super().__init__(inspector, backend or PydanticDTOBackend(AggregateFilterDTO), handle_cycles, type_map)
        self.aggregation_builder = aggregation_builder or AggregationInspector(inspector)
        self._filter_function_builder = PydanticDTOBackend(AggregationFunctionFilterDTO)

    @override
    def type_description(self) -> str:
        return "Boolean expression to compare aggregated fields. All fields are combined with logical 'AND'."

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateFilterDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}AggregateBoolExp"

    def _aggregate_function_type(
        self,
        model: type[T],
        dto_config: DTOConfig,
        dto_name: str,
        aggregation: FilterFunctionInfo[T, ModelFieldT, OrderComparison[Any, Any, Any]],
        model_field: DTOMissingType | ModelFieldT,
        parent_field_def: DTOFieldDefinition[ModelT, Any] | None,
    ) -> type[AggregationFunctionFilterDTO[ModelT]]:
        dto_config = DTOConfig(Purpose.WRITE)
        dto = self._filter_function_builder.build(
            name=f"{dto_name}{snake_to_camel(aggregation.field_name).capitalize()}",
            model=model,
            field_definitions=[
                FunctionArgFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name="arguments",
                    type_hint=list[aggregation.enum_fields]
                    if aggregation.require_arguments
                    else list[aggregation.enum_fields] | None,
                    default_factory=DTO_MISSING if aggregation.require_arguments else list,
                    _function=aggregation,
                    _model_field=model_field,
                ),
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name="distinct",
                    type_hint=bool | None,
                    default=False,
                    _function=aggregation,
                    _model_field=model_field,
                ),
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name="predicate",
                    type_hint=aggregation.comparison_type,
                    _function=aggregation,
                    _model_field=model_field,
                ),
            ],
        )
        key = DTOKey([model])
        dto.__strawchemy_field_map__ = {
            key + name: FunctionArgFieldDefinition.from_field(field, function=aggregation)
            for name, field in self.inspector.field_definitions(model, dto_config)
        }
        dto.__strawchemy_description__ = "Field filtering information"
        dto.__dto_function_info__ = aggregation
        return dto

    @override
    def _factory(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateFilterDTO[ModelT]], None],
        base: type[Any] | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO[ModelT]]:
        function_aliases: dict[str, AggregationFunction] = {}
        field_defs: list[GraphQLFieldDefinition[T, ModelFieldT]] = []
        model_field = DTO_MISSING if parent_field_def is None else parent_field_def.model_field
        for aggregation in self.aggregation_builder.filter_functions(model, dto_config):
            if aggregation.function != aggregation.field_name:
                function_aliases[aggregation.field_name] = aggregation.function
            field_defs.append(
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name=aggregation.field_name,
                    type_hint=self._aggregate_function_type(
                        model=model,
                        dto_config=dto_config,
                        dto_name=name,
                        parent_field_def=parent_field_def,
                        model_field=model_field,
                        aggregation=aggregation,
                    ),
                    _model_field=model_field,
                    _function=aggregation,
                ),
            )
        key = DTOKey([model])
        dto = self.backend.build(name, model, field_defs, **(backend_kwargs or {}))
        dto.__strawchemy_description__ = (
            "Boolean expression to compare field aggregations. All fields are combined with logical 'AND'."
        )
        dto.__strawchemy_field_map__ = {key + field.name: field for field in field_defs}
        return dto


class OrderByDTOFactory(FilterDTOFactory[ModelT, ModelFieldT, OrderByDTO[ModelT, ModelFieldT]]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        backend: DTOBackend[OrderByDTO[ModelT, ModelFieldT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterDTOFactory[ModelT, ModelFieldT] | None = None,
    ) -> None:
        super().__init__(
            inspector,
            backend or PydanticDTOBackend(OrderByDTO),
            handle_cycles,
            type_map,
            aggregation_filter_factory,
        )

    @override
    def _filter_type(self, field: DTOFieldDefinition[T, ModelFieldT]) -> type[OrderByEnum]:
        return OrderByEnum

    def _order_by_aggregation_fields(
        self,
        aggregation: FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]],
        model: type[Any],
        dto_config: DTOConfig,
    ) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        field_defs = [
            FunctionArgFieldDefinition(
                dto_config=dto_config,
                model=model,
                model_field_name=name.field_definition.name,
                type_hint=OrderByEnum,
                _function=aggregation,
            )
            for name in aggregation.enum_fields
        ]

        name = f"{model.__name__}Aggregate{snake_to_camel(aggregation.aggregation_type)}FieldsOrderBy"
        dto = self.backend.build(name, model, field_defs)
        key = DTOKey([model])
        dto.__strawchemy_field_map__ = {
            key + name: FunctionArgFieldDefinition.from_field(field, function=aggregation)
            for name, field in self.inspector.field_definitions(model, dto_config)
        }
        return dto

    def _order_by_aggregation(self, model: type[Any], dto_config: DTOConfig) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        field_definitions: list[GraphQLFieldDefinition[ModelT, ModelFieldT]] = []
        for aggregation in self._aggregation_filter_factory.aggregation_builder.filter_functions(model, dto_config):
            if aggregation.require_arguments:
                type_hint = self._order_by_aggregation_fields(aggregation, model, dto_config)
            else:
                type_hint = OrderByEnum
            dto_config = DTOConfig(
                dto_config.purpose, aliases={aggregation.function: aggregation.field_name}, partial=dto_config.partial
            )
            field_definitions.append(
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name=aggregation.field_name,
                    type_hint=type_hint,
                    _function=aggregation,
                )
            )

        dto = self.backend.build(f"{model.__name__}AggregateOrderBy", model, field_definitions)
        dto.__strawchemy_field_map__ = {DTOKey([model, field.name]): field for field in field_definitions}
        return dto

    @override
    def _aggregation_field(
        self, field_def: DTOFieldDefinition[ModelT, ModelFieldT], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition[ModelT, ModelFieldT]:
        related_model = self.inspector.relation_model(field_def.model_field)
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=related_model,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=self._order_by_aggregation(related_model, dto_config),
        )

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, OrderByDTO[ModelT, ModelFieldT]], None] | None = None,
    ) -> str:
        return f"{base_name}OrderBy"

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, OrderByDTO[ModelT, ModelFieldT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            aggregate_filters=aggregate_filters,
            **kwargs,
        )
        dto.__strawchemy_description__ = "Ordering options"
        return dto
