from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, override

from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelFieldT, ModelInspector, ModelT, Relation
from strawchemy.dto.exceptions import DTOError
from strawchemy.graphql.dto import (
    DTOKey,
    EnumDTO,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    GraphQLFieldDefinition,
    OutputFunctionInfo,
    UnmappedDataclassGraphQLDTO,
)

from .base import GraphQLDTOFactory
from .enum import EnumDTOBackend, EnumDTOFactory

if TYPE_CHECKING:
    from collections.abc import Generator

    from strawchemy.dto.types import DTOConfig
    from strawchemy.graph import Node
    from strawchemy.graphql.filters import OrderComparison
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol
    from strawchemy.graphql.typing import AggregationType, FunctionInfo

T = TypeVar("T")


class _CountFieldsDTOFactory(EnumDTOFactory[ModelT, ModelFieldT]):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}CountFields"


class _FunctionArgDTOFactory(GraphQLDTOFactory[ModelT, ModelFieldT, UnmappedDataclassGraphQLDTO[ModelT]]):
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
        self._enum_backend = EnumDTOBackend()

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
        *,
        field_map: dict[DTOKey, GraphQLFieldDefinition[Any, Any]] | None = None,
        function: FunctionInfo[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            yield (FunctionArgFieldDefinition.from_field(field, function=function) if function is not None else field)

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
        *,
        function: FunctionInfo[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> type[UnmappedDataclassGraphQLDTO[ModelT]]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            function=function,
            **kwargs,
        )

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
            name = f"{self.dto_name(model.__name__, dto_config)}Enum"
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
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}NumericFields"


class _MinMaxFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, str, Decimal, date, datetime, time}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxFields"


class _MinMaxDateFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {date}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxDateFields"


class _MinMaxDateTimeFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {datetime}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxDateTimeFields"


class _MinMaxNumericFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, Decimal}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxNumericFields"


class _MinMaxStringFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {str}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxStringFields"


class _MinMaxTimeFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {time}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}MinMaxTimeFields"


class _SumFieldsDTOFactory(_FunctionArgDTOFactory[ModelT, ModelFieldT]):
    types: ClassVar[set[type[Any]]] = {int, float, str, Decimal, timedelta}

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedDataclassGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}SumFields"


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
    ) -> list[FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]]]:
        count_fields = self._count_fields_factory.factory(model=model, dto_config=dto_config)
        numeric_arg_fields = self.arguments_type(model, dto_config, "numeric")
        sum_arg_fields = self.arguments_type(model, dto_config, "sum")

        aggregations: list[FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]]] = [
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
