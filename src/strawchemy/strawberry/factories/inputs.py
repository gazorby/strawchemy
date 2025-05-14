from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any, TypeVar, override

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry import UNSET
from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, Relation
from strawchemy.dto.types import DTO_MISSING, DTOConfig, DTOMissingType, Purpose
from strawchemy.graph import Node
from strawchemy.strawberry._registry import RegistryTypeInfo
from strawchemy.strawberry.dto import (
    AggregateFieldDefinition,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    BooleanFilterDTO,
    DTOKey,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
)
from strawchemy.strawberry.typing import AggregationFunction, GraphQLFilterDTOT
from strawchemy.utils import snake_to_camel

from .aggregations import AggregationInspector
from .base import StrawchemyUnMappedDTOFactory, UnmappedGraphQLDTOT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelFieldT, Relation
    from strawchemy.dto.types import ExcludeFields, IncludeFields
    from strawchemy.graph import Node
    from strawchemy.sqlalchemy.typing import DeclarativeT
    from strawchemy.strawberry.filters import GraphQLFilter
    from strawchemy.strawberry.typing import GraphQLType


T = TypeVar("T")


class _BaseStrawchemyFilterFactory(StrawchemyUnMappedDTOFactory[UnmappedGraphQLDTOT]):
    @classmethod
    @override
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        return "input"

    @override
    def input(
        self,
        model: type[DeclarativeT],
        *,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        purpose: Purpose = Purpose.READ,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[UnmappedGraphQLDTOT]]:
        return self._input_wrapper(
            model=model,
            include=include,
            exclude=exclude,
            partial=partial,
            type_map=type_map,
            aliases=aliases,
            alias_generator=alias_generator,
            name=name,
            description=description,
            directives=directives,
            override=override,
            purpose=purpose,
            **kwargs,
        )


class _FilterDTOFactory(_BaseStrawchemyFilterFactory[GraphQLFilterDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[GraphQLFilterDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterDTOFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_filter_factory = aggregation_filter_factory or AggregateFilterDTOFactory(mapper)

    def _filter_type(self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]) -> type[GraphQLFilter]:
        return self.inspector.get_field_comparison(field)

    def _aggregation_field(
        self, field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition:
        related_model = self.inspector.relation_model(field_def.model_field)
        type_hint = self._aggregation_filter_factory.factory(
            model=related_model, dto_config=dto_config, parent_field_def=field_def
        )
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=related_model,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=type_hint | None,
            default=UNSET,
        )

    @override
    def type_description(self) -> str:
        return "Boolean expression to compare fields. All fields are combined with logical 'AND'."

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, GraphQLFilterDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        aggregate_filters: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], None, None]:
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

            field.default = UNSET
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
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


class BooleanFilterDTOFactory(_FilterDTOFactory[BooleanFilterDTO]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[BooleanFilterDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregate_filter_factory: AggregateFilterDTOFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(BooleanFilterDTO),
            handle_cycles,
            type_map,
            aggregation_filter_factory=aggregate_filter_factory,
            **kwargs,
        )


class AggregateFilterDTOFactory(_BaseStrawchemyFilterFactory[AggregateFilterDTO]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[AggregateFilterDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_builder: AggregationInspector | None = None,
    ) -> None:
        super().__init__(mapper, backend or StrawberrryDTOBackend(AggregateFilterDTO), handle_cycles, type_map)
        self.aggregation_builder = aggregation_builder or AggregationInspector(mapper)
        self._filter_function_builder = StrawberrryDTOBackend(AggregationFunctionFilterDTO)

    @override
    def type_description(self) -> str:
        return "Boolean expression to compare aggregated fields. All fields are combined with logical 'AND'."

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateFilterDTO], None] | None = None,
    ) -> str:
        return f"{base_name}AggregateBoolExp"

    def _aggregate_function_type(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        dto_name: str,
        aggregation: FilterFunctionInfo,
        model_field: DTOMissingType | QueryableAttribute[Any],
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None,
    ) -> type[AggregationFunctionFilterDTO]:
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
        return self._mapper.registry.register_type(
            dto,
            RegistryTypeInfo(dto.__name__, "input"),
            description=f"Boolean expression to compare {aggregation.function} aggregation.",
        )

    @override
    def _factory(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateFilterDTO], None],
        base: type[Any] | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO]:
        function_aliases: dict[str, AggregationFunction] = {}
        field_defs: list[GraphQLFieldDefinition] = []
        model_field = DTO_MISSING if parent_field_def is None else parent_field_def.model_field
        for aggregation in self.aggregation_builder.filter_functions(model, dto_config):
            if aggregation.function != aggregation.field_name:
                function_aliases[aggregation.field_name] = aggregation.function
            type_hint = self._aggregate_function_type(
                model=model,
                dto_config=dto_config,
                dto_name=name,
                parent_field_def=parent_field_def,
                model_field=model_field,
                aggregation=aggregation,
            )
            field_defs.append(
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name=aggregation.field_name,
                    type_hint=type_hint | None,
                    default=UNSET,
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


class OrderByDTOFactory(_FilterDTOFactory[OrderByDTO]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[OrderByDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterDTOFactory | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(OrderByDTO),
            handle_cycles,
            type_map,
            aggregation_filter_factory,
        )

    @override
    def _filter_type(self, field: DTOFieldDefinition[T, ModelFieldT]) -> type[OrderByEnum]:
        return OrderByEnum

    def _order_by_aggregation_fields(
        self,
        aggregation: FilterFunctionInfo,
        model: type[Any],
        dto_config: DTOConfig,
    ) -> type[OrderByDTO]:
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
        return self._mapper.registry.register_type(dto, RegistryTypeInfo(dto.__name__, "input"))

    def _order_by_aggregation(self, model: type[Any], dto_config: DTOConfig) -> type[OrderByDTO]:
        field_definitions: list[GraphQLFieldDefinition] = []
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
                    type_hint=type_hint | None,
                    default=UNSET,
                    _function=aggregation,
                )
            )

        dto = self.backend.build(f"{model.__name__}AggregateOrderBy", model, field_definitions)
        dto.__strawchemy_field_map__ = {DTOKey([model, field.name]): field for field in field_definitions}
        return self._mapper.registry.register_type(dto, RegistryTypeInfo(dto.__name__, "input"))

    @override
    def _aggregation_field(
        self, field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition:
        related_model = self.inspector.relation_model(field_def.model_field)
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=related_model,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=self._order_by_aggregation(related_model, dto_config) | None,
            default=UNSET,
        )

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, OrderByDTO], None] | None = None,
    ) -> str:
        return f"{base_name}OrderBy"

    @override
    def factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, OrderByDTO], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[OrderByDTO]:
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
