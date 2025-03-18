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

import dataclasses
from collections.abc import Generator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from inspect import getmodule
from types import new_class
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast, override

from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.backend.pydantic import PydanticDTOBackend
from strawchemy.dto.base import (
    DTOBackend,
    DTOBase,
    DTOBaseT,
    DTOFactory,
    DTOFieldDefinition,
    ModelFieldT,
    ModelInspector,
    ModelT,
    Relation,
)
from strawchemy.dto.exceptions import DTOError
from strawchemy.dto.types import DTO_MISSING, DTOConfig, DTOMissingType, ExcludeFields, IncludeFields, Purpose
from strawchemy.graph import Node
from strawchemy.utils import snake_to_camel, snake_to_lower_camel_case

from . import typing as strawchemy_typing
from .constants import AGGREGATIONS_KEY, NODES_KEY
from .dto import (
    AggregateDTO,
    AggregateFieldDefinition,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    DTOKey,
    EnumDTO,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    OutputFunctionInfo,
    UnmappedDataclassGraphQLDTO,
)
from .typing import AggregateDTOT, FunctionInfo, GraphQLDTOT, GraphQLFilterDTOT

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

    from strawchemy.graph import Node

    from .filters import GraphQLFilter, NumericComparison
    from .inspector import GraphQLInspectorProtocol
    from .typing import AggregationFunction, AggregationType


__all__ = (
    "AggregateDTOFactory",
    "AggregateFilterDTOFactory",
    "AggregationInspector",
    "DistinctOnFieldsDTOFactory",
    "FilterDTOFactory",
    "FilterFunctionInfo",
    "OrderByDTOFactory",
    "OutputFunctionInfo",
    "RootAggregateTypeDTOFactory",
    "TypeDTOFactory",
)

T = TypeVar("T")


_TYPING_NS = vars(strawchemy_typing)


class _EnumDTOBackend(DTOBackend[EnumDTO], Generic[ModelT]):
    def __init__(self, to_camel: bool = True) -> None:
        self.dto_base = EnumDTO
        self.to_camel = to_camel

    @override
    def build(
        self,
        name: str,
        model: type[T],
        field_definitions: Iterable[DTOFieldDefinition[ModelT, ModelFieldT]],
        base: type[Any] | None = None,
        **kwargs: Any,
    ) -> type[EnumDTO]:
        field_map = {
            snake_to_lower_camel_case(field.name) if self.to_camel else field.name: field for field in field_definitions
        }

        def exec_body(namespace: dict[str, Any]) -> Any:
            def to_field_definition(self: EnumDTO) -> DTOFieldDefinition[ModelT, ModelFieldT]:
                return self.__field_definitions__[self.value]

            namespace["field_definition"] = property(to_field_definition)
            namespace["__field_definitions__"] = field_map

        base = new_class(name=f"{name}Base", bases=(DTOBase,), exec_body=exec_body)
        module = __name__
        if model_module := getmodule(model):
            module = model_module.__name__
        return cast(
            type[EnumDTO],
            EnumDTO(value=name, names=[(value, value) for value in list(field_map)], type=base, module=module),
        )

    @override
    @classmethod
    def copy(cls, dto: type[EnumDTO], name: str) -> EnumDTO:  # pyright: ignore[reportIncompatibleMethodOverride]
        enum = EnumDTO(value=name, names=[(value.name, value.value) for value in dto])
        enum.__field_definitions__ = dto.__field_definitions__
        return enum


class _EnumDTOFactory(DTOFactory[ModelT, ModelFieldT, EnumDTO]):
    def __init__(
        self,
        inspector: ModelInspector[Any, ModelFieldT],
        backend: DTOBackend[EnumDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(inspector, backend or _EnumDTOBackend(), handle_cycles, type_map)

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}Fields"

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, ModelFieldT],
        dto_config: DTOConfig,
        node: Node[Relation[Any, EnumDTO], None],
        has_override: bool,
    ) -> bool:
        return super().should_exclude_field(field, dto_config, node, has_override) or field.is_relation

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, EnumDTO], None],
        raise_if_no_fields: bool = False,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            yield GraphQLFieldDefinition.from_field(field)

    @override
    def decorator(
        self,
        model: type[T],
        purpose: Purpose = Purpose.READ,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[EnumDTO]]:
        return super().decorator(
            model,
            purpose,
            include=include,
            exclude=exclude,
            partial=partial,
            aliases=aliases,
            alias_generator=alias_generator,
            type_map=type_map,
            **kwargs,
        )


class _CountFieldsDTOFactory(_EnumDTOFactory[ModelT, ModelFieldT]):
    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}CountFields"


class _GraphQLDTOFactory(DTOFactory[ModelT, ModelFieldT, DTOBaseT]):
    inspector: GraphQLInspectorProtocol[Any, ModelFieldT]

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
        node: Node[Relation[ModelT, DTOBaseT], None],
        raise_if_no_fields: bool = False,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            yield GraphQLFieldDefinition.from_field(field)


class _FunctionArgDTOFactory(_GraphQLDTOFactory[ModelT, ModelFieldT, UnmappedDataclassGraphQLDTO[ModelT]]):
    types: ClassVar[set[type[Any]]] = set()

    def __init__(
        self,
        inspector: ModelInspector[Any, ModelFieldT],
        backend: DTOBackend[UnmappedDataclassGraphQLDTO[ModelT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            inspector, backend or DataclassDTOBackend(UnmappedDataclassGraphQLDTO), handle_cycles, type_map
        )
        self._enum_backend = _EnumDTOBackend()

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, ModelFieldT],
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None],
        has_override: bool = False,
    ) -> bool:
        return (
            super().should_exclude_field(field, dto_config, node, has_override)
            or field.is_relation
            or self.inspector.model_field_type(field) not in self.types
        )

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, UnmappedDataclassGraphQLDTO[ModelT]], None],
        raise_if_no_fields: bool = False,
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
        function: FunctionInfo[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            key = DTOKey.from_dto_node(node)
            field_def = (
                FunctionArgFieldDefinition.from_field(field, function=function) if function is not None else field
            )
            yield field_def
            field_map[key + field_def.name] = field_def

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        function: FunctionInfo[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> type[UnmappedDataclassGraphQLDTO[ModelT]]:
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
            function=function,
            **kwargs,
        )
        if not dto.__strawchemy_field_map__:
            dto.__strawchemy_field_map__ = field_map
        return dto

    def enum_factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        name: str | None = None,
        base: type[Any] | None = None,
        raise_if_no_fields: bool = False,
        **kwargs: Any,
    ) -> type[EnumDTO]:
        if not name:
            name = f"{self.dto_name_suffix(model.__name__, dto_config)}Enum"
        field_defs = self.iter_field_definitions(
            name=name,
            model=model,
            dto_config=dto_config,
            base=base,
            node=self._node_or_root(model, name, None),
            raise_if_no_fields=raise_if_no_fields,
            **kwargs,
        )
        return self._enum_backend.build(name, model, list(field_defs), base)


class _NumericFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, Decimal}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}NumericFields"


class _MinMaxFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, str, Decimal, date, datetime, time}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxFields"


class _MinMaxDateFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {date}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxDateFields"


class _MinMaxDateTimeFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {datetime}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxDateTimeFields"


class _MinMaxNumericFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, Decimal}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxNumericFields"


class _MinMaxStringFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {str}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxStringFields"


class _MinMaxTimeFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {time}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}MinMaxTimeFields"


class _SumFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, str, Decimal, timedelta}

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}SumFields"


class AggregationInspector(Generic[ModelT, ModelFieldT]):
    def __init__(self, inspector: GraphQLInspectorProtocol[Any, ModelFieldT]) -> None:
        self._inspector = inspector
        self._count_fields_factory = _CountFieldsDTOFactory(inspector)
        self._numeric_fields_factory = _NumericFieldsDTOFactory(inspector)
        self._sum_fields_factory = _SumFieldsDTOFactory(inspector)
        self._min_max_numeric_fields_factory = _MinMaxNumericFieldsDTOFactory(inspector)
        self._min_max_datetime_fields_factory = _MinMaxDateTimeFieldsDTOFactory(inspector)
        self._min_max_date_fields_factory = _MinMaxDateFieldsDTOFactory(inspector)
        self._min_max_string_fields_factory = _MinMaxStringFieldsDTOFactory(inspector)
        self._min_max_time_fields_factory = _MinMaxTimeFieldsDTOFactory(inspector)
        self._min_max_fields_factory = _MinMaxFieldsDTOFactory(inspector)

    def arguments_type(
        self, model: type[T], dto_config: DTOConfig, aggregation: AggregationType
    ) -> type[EnumDTO] | None:
        try:
            if aggregation == "numeric":
                dto = self._numeric_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "sum":
                dto = self._sum_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "min_max_date":
                dto = self._min_max_date_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "min_max_datetime":
                dto = self._min_max_datetime_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "min_max_string":
                dto = self._min_max_string_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "min_max_numeric":
                dto = self._min_max_numeric_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
            elif aggregation == "min_max_time":
                dto = self._min_max_time_fields_factory.enum_factory(model, dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def numeric_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        try:
            dto = self._numeric_fields_factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def min_max_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        try:
            dto = self._min_max_fields_factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def sum_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        try:
            dto = self._sum_fields_factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def output_functions(self, model: type[Any], dto_config: DTOConfig) -> list[OutputFunctionInfo]:
        int_as_float_config = dataclasses.replace(
            dto_config, type_overrides={int: float | None, int | None: float | None}
        )
        numeric_fields = self.numeric_field_type(model, int_as_float_config)
        min_max_fields = self.min_max_field_type(model, dto_config)
        sum_fields = self.sum_field_type(model, dto_config)

        aggregations: list[OutputFunctionInfo] = [
            OutputFunctionInfo(
                function="count", require_arguments=False, output_type=int | None if dto_config.partial else int
            )
        ]

        if sum_fields:
            aggregations.append(OutputFunctionInfo(function="sum", output_type=sum_fields))
        if min_max_fields:
            aggregations.extend(
                [
                    OutputFunctionInfo(function="min", output_type=min_max_fields),
                    OutputFunctionInfo(function="max", output_type=min_max_fields),
                ]
            )

        if numeric_fields:
            aggregations.extend(
                [
                    OutputFunctionInfo(function="avg", output_type=numeric_fields),
                    OutputFunctionInfo(function="stddev", output_type=numeric_fields),
                    OutputFunctionInfo(function="stddev_samp", output_type=numeric_fields),
                    OutputFunctionInfo(function="stddev_pop", output_type=numeric_fields),
                    OutputFunctionInfo(function="variance", output_type=numeric_fields),
                    OutputFunctionInfo(function="var_samp", output_type=numeric_fields),
                    OutputFunctionInfo(function="var_pop", output_type=numeric_fields),
                ]
            )
        return aggregations

    def filter_functions(
        self, model: type[Any], dto_config: DTOConfig
    ) -> list[FilterFunctionInfo[ModelT, ModelFieldT, NumericComparison[Any, Any, Any]]]:
        count_fields = self._count_fields_factory.factory(model=model, dto_config=dto_config)
        numeric_arg_fields = self.arguments_type(model, dto_config, "numeric")
        sum_arg_fields = self.arguments_type(model, dto_config, "sum")

        aggregations: list[FilterFunctionInfo[ModelT, ModelFieldT, NumericComparison[Any, Any, Any]]] = [
            FilterFunctionInfo(
                enum_fields=count_fields,
                function="count",
                aggregation_type="numeric",
                comparison_type=self._inspector.get_type_comparison(int),
                require_arguments=False,
            )
        ]
        if sum_arg_fields:
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=sum_arg_fields,
                    function="sum",
                    aggregation_type="numeric",
                    comparison_type=self._inspector.get_type_comparison(float),
                )
            )
        if min_max_numeric_fields := self.arguments_type(model, dto_config, "min_max_numeric"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_numeric_fields,
                    function="min",
                    aggregation_type="numeric",
                    comparison_type=self._inspector.get_type_comparison(float),
                )
            )
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_numeric_fields,
                    function="max",
                    aggregation_type="numeric",
                    comparison_type=self._inspector.get_type_comparison(float),
                )
            )
        if min_max_datetime_fields := self.arguments_type(model, dto_config, "min_max_datetime"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_datetime_fields,
                    function="min",
                    aggregation_type="min_max_datetime",
                    comparison_type=self._inspector.get_type_comparison(datetime),
                    field_name_="min_datetime",
                )
            )
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_datetime_fields,
                    function="max",
                    aggregation_type="min_max_datetime",
                    comparison_type=self._inspector.get_type_comparison(datetime),
                    field_name_="max_datetime",
                )
            )
        if min_max_date_fields := self.arguments_type(model, dto_config, "min_max_date"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_date_fields,
                    function="min",
                    aggregation_type="min_max_date",
                    comparison_type=self._inspector.get_type_comparison(date),
                    field_name_="min_date",
                )
            )
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_date_fields,
                    function="max",
                    aggregation_type="min_max_date",
                    comparison_type=self._inspector.get_type_comparison(date),
                    field_name_="max_date",
                )
            )
        if min_max_time_fields := self.arguments_type(model, dto_config, "min_max_time"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_time_fields,
                    function="min",
                    aggregation_type="min_max_time",
                    comparison_type=self._inspector.get_type_comparison(time),
                    field_name_="min_time",
                )
            )
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_time_fields,
                    function="max",
                    aggregation_type="min_max_time",
                    comparison_type=self._inspector.get_type_comparison(time),
                    field_name_="max_time",
                )
            )
        if min_max_string_fields := self.arguments_type(model, dto_config, "min_max_string"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_string_fields,
                    function="min",
                    aggregation_type="min_max_string",
                    comparison_type=self._inspector.get_type_comparison(str),
                    field_name_="min_string",
                )
            )
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=min_max_string_fields,
                    function="max",
                    aggregation_type="min_max_string",
                    comparison_type=self._inspector.get_type_comparison(str),
                    field_name_="max_string",
                )
            )
        if numeric_arg_fields:
            comparison = self._inspector.get_type_comparison(float)
            aggregations.extend(
                [
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="avg",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="stddev",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="stddev_samp",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="stddev_pop",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="variance",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="var_samp",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function="var_pop",
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    ),
                ]
            )
        return aggregations


class TypeDTOFactory(_GraphQLDTOFactory[ModelT, ModelFieldT, GraphQLDTOT]):
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
    ) -> DTOFieldDefinition[ModelT, ModelFieldT]:
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
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}{'Input' if dto_config.purpose is Purpose.WRITE else ''}Type"

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
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(name, model, dto_config, base, node, raise_if_no_fields, **kwargs):
            key = DTOKey.from_dto_node(node)
            if field.is_relation and field.uselist and aggregations:
                aggregation_field = self._aggregation_field(field, dto_config)
                field_map[key + aggregation_field.name] = aggregation_field
                yield aggregation_field
            yield field
            field_map[key + field.name] = field

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
            aggregations=aggregations,
            field_map=field_map,
            **kwargs,
        )
        if not dto.__strawchemy_field_map__:
            dto.__strawchemy_field_map__ = field_map
        return dto


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
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}Root"

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
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
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


class FilterDTOFactory(_GraphQLDTOFactory[ModelT, ModelFieldT, GraphQLFilterDTOT]):
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
    ) -> DTOFieldDefinition[ModelT, ModelFieldT]:
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
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            key = DTOKey.from_dto_node(node)
            field_name = field.name
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
            field_map[key + field_name] = field
            yield field

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}BoolExp"

    @override
    def decorator(
        self,
        model: type[T],
        purpose: Purpose,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[GraphQLFilterDTOT]]:
        return super().decorator(
            model, purpose, include, exclude, partial, type_map, aliases, alias_generator, **kwargs
        )

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
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[GraphQLFilterDTOT]:
        kwargs.pop("field_map", None)
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
            aggregate_filters=aggregate_filters,
            field_map=field_map,
            **kwargs,
        )
        if not dto.__strawchemy_field_map__:
            dto.__strawchemy_field_map__ = field_map
        dto.__strawchemy_description__ = (
            "Boolean expression to compare fields. All fields are combined with logical 'AND'."
        )
        return dto


class AggregateDTOFactory(_GraphQLDTOFactory[ModelT, ModelFieldT, AggregateDTOT]):
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
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}Aggregate"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, AggregateDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            key = DTOKey.from_dto_node(node)
            field_map[key + field.name] = field
            yield field

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
        field_map: dict[DTOKey, DTOFieldDefinition[Any, Any]] | None = None,
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

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, AggregateDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[AggregateDTOT]:
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
        dto.__strawchemy_description__ = "Aggregation fields"
        return dto


class AggregateFilterDTOFactory(_GraphQLDTOFactory[ModelT, ModelFieldT, AggregateFilterDTO[ModelT]]):
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
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}AggregateBoolExp"

    @override
    def decorator(
        self,
        model: type[T],
        purpose: Purpose,
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[AggregateFilterDTO[ModelT]]]:
        return super().decorator(
            model, purpose, include, exclude, partial, type_map, aliases, alias_generator, **kwargs
        )

    def _aggregate_function_type(
        self,
        model: type[T],
        dto_config: DTOConfig,
        dto_name: str,
        aggregation: FilterFunctionInfo[T, ModelFieldT, NumericComparison[Any, Any, Any]],
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

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, AggregateFilterDTO[ModelT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO[ModelT]]:
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
        dto.__strawchemy_description__ = (
            "Boolean expression to compare aggregated fields. All fields are combined with logical 'AND'."
        )
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
        aggregation: FilterFunctionInfo[ModelT, ModelFieldT, NumericComparison[Any, Any, Any]],
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
    ) -> DTOFieldDefinition[ModelT, ModelFieldT]:
        related_model = self.inspector.relation_model(field_def.model_field)
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=related_model,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=self._order_by_aggregation(related_model, dto_config),
        )

    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}OrderBy"

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
            aggregate_filters,
            **kwargs,
        )
        dto.__strawchemy_description__ = "Ordering options"
        return dto


class DistinctOnFieldsDTOFactory(_EnumDTOFactory[ModelT, ModelFieldT]):
    @override
    def dto_name_suffix(self, name: str, dto_config: DTOConfig) -> str:
        return f"{name}DistinctOnFields"
