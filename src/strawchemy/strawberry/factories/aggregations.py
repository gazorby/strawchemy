from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Optional, TypeVar, cast

from sqlalchemy.orm import DeclarativeBase
from typing_extensions import override

from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.exceptions import DTOError
from strawchemy.strawberry.dto import (
    DTOKey,
    EnumDTO,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    GraphQLFieldDefinition,
    OutputFunctionInfo,
    UnmappedStrawberryGraphQLDTO,
)
from strawchemy.strawberry.factories.base import GraphQLDTOFactory
from strawchemy.strawberry.factories.enum import EnumDTOBackend, EnumDTOFactory

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.orm import QueryableAttribute

    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelT, Relation
    from strawchemy.dto.types import DTOConfig
    from strawchemy.graph import Node
    from strawchemy.mapper import Strawchemy
    from strawchemy.sqlalchemy.typing import DeclarativeT
    from strawchemy.strawberry.typing import AggregationFunction, AggregationType, FunctionInfo

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _TypeFilterConfig:
    """Configuration for type-filtered DTO factories.

    Attributes:
        types: Set of Python types to filter fields by.
        suffix: Suffix to append to the base name for DTO naming.
    """

    suffix: str
    types: frozenset[type[Any]] = field(default_factory=frozenset)


class _CountFieldsDTOFactory(EnumDTOFactory):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}CountFields"


class _FunctionArgDTOFactory(GraphQLDTOFactory[UnmappedStrawberryGraphQLDTO[DeclarativeBase]]):
    types: ClassVar[set[type[Any]]] = set()

    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper, backend or StrawberrryDTOBackend(UnmappedStrawberryGraphQLDTO), handle_cycles, type_map
        )
        self._enum_backend = EnumDTOBackend()

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedStrawberryGraphQLDTO[DeclarativeBase]], None],
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, UnmappedStrawberryGraphQLDTO[DeclarativeBase]], None],
        raise_if_no_fields: bool = False,
        *,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        function: FunctionInfo | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        for field_def in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, field_map=field_map, **kwargs
        ):
            yield (
                FunctionArgFieldDefinition.from_field(field_def, function=function)
                if function is not None
                else field_def
            )

    @override
    def factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, UnmappedStrawberryGraphQLDTO[DeclarativeBase]], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        function: FunctionInfo | None = None,
        **kwargs: Any,
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags,
            backend_kwargs,
            function=function,
            **kwargs,
        )

    def enum_factory(
        self,
        model: type[DeclarativeT],
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


class _TypeFilteredFunctionArgDTOFactory(_FunctionArgDTOFactory):
    """Generic factory for type-filtered aggregation field DTOs.

    This factory replaces multiple nearly-identical factory classes by using
    a configuration object to specify the types and naming suffix.
    """

    def __init__(
        self,
        mapper: Strawchemy,
        filter_config: _TypeFilterConfig,
        backend: DTOBackend[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None = None,
    ) -> None:
        super().__init__(mapper, backend)
        self._filter_types = set(filter_config.types)
        self._suffix = filter_config.suffix

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedStrawberryGraphQLDTO[DeclarativeBase]], None],
        has_override: bool = False,
    ) -> bool:
        return (
            super(_FunctionArgDTOFactory, self).should_exclude_field(field, dto_config, node, has_override)
            or field.is_relation
            or self.inspector.model_field_type(field) not in self._filter_types
        )

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, UnmappedStrawberryGraphQLDTO[ModelT]], None] | None = None,
    ) -> str:
        return f"{base_name}{self._suffix}"


class AggregationInspector:
    _aggregation_type_filters: ClassVar[dict[str, _TypeFilterConfig]] = {
        "numeric": _TypeFilterConfig("NumericFields", frozenset({int, float, Decimal})),
        "sum": _TypeFilterConfig("SumFields", frozenset({int, float, str, Decimal, timedelta})),
        "min_max": _TypeFilterConfig("MinMaxFields", frozenset({int, float, str, Decimal, date, datetime, time})),
        "min_max_numeric": _TypeFilterConfig("MinMaxNumericFields", frozenset({int, float, Decimal})),
        "min_max_datetime": _TypeFilterConfig("MinMaxDateTimeFields", frozenset({datetime})),
        "min_max_date": _TypeFilterConfig("MinMaxDateFields", frozenset({date})),
        "min_max_string": _TypeFilterConfig("MinMaxStringFields", frozenset({str})),
        "min_max_time": _TypeFilterConfig("MinMaxTimeFields", frozenset({time})),
    }

    def __init__(self, mapper: Strawchemy) -> None:
        self._inspector = mapper.config.inspector
        self._count_fields_factory = _CountFieldsDTOFactory(self._inspector)

        # Create type-filtered factories from configuration
        self._type_filtered_factories: dict[str, _TypeFilteredFunctionArgDTOFactory] = {
            key: _TypeFilteredFunctionArgDTOFactory(mapper, config)
            for key, config in self._aggregation_type_filters.items()
        }

    def _supports_aggregations(self, *function: AggregationFunction) -> bool:
        return set(function).issubset(self._inspector.db_features.aggregation_functions)

    @cached_property
    def _statistical_aggregations(self) -> list[AggregationFunction]:
        return list(
            self._inspector.db_features.aggregation_functions
            - cast("set[AggregationFunction]", {"min", "max", "sum", "count"})
        )

    def _min_max_filters(self, model: type[DeclarativeBase], dto_config: DTOConfig) -> list[FilterFunctionInfo]:
        aggregations: list[FilterFunctionInfo] = []

        if min_max_numeric_fields := self.arguments_type(model, dto_config, "min_max_numeric"):
            aggregations.extend(
                (
                    FilterFunctionInfo(
                        enum_fields=min_max_numeric_fields,
                        function="min",
                        aggregation_type="numeric",
                        comparison_type=self._inspector.get_type_comparison(float),
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_numeric_fields,
                        function="max",
                        aggregation_type="numeric",
                        comparison_type=self._inspector.get_type_comparison(float),
                    ),
                )
            )
        if min_max_datetime_fields := self.arguments_type(model, dto_config, "min_max_datetime"):
            aggregations.extend(
                (
                    FilterFunctionInfo(
                        enum_fields=min_max_datetime_fields,
                        function="min",
                        aggregation_type="min_max_datetime",
                        comparison_type=self._inspector.get_type_comparison(datetime),
                        field_name_="min_datetime",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_datetime_fields,
                        function="max",
                        aggregation_type="min_max_datetime",
                        comparison_type=self._inspector.get_type_comparison(datetime),
                        field_name_="max_datetime",
                    ),
                )
            )
        if min_max_date_fields := self.arguments_type(model, dto_config, "min_max_date"):
            aggregations.extend(
                (
                    FilterFunctionInfo(
                        enum_fields=min_max_date_fields,
                        function="min",
                        aggregation_type="min_max_date",
                        comparison_type=self._inspector.get_type_comparison(date),
                        field_name_="min_date",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_date_fields,
                        function="max",
                        aggregation_type="min_max_date",
                        comparison_type=self._inspector.get_type_comparison(date),
                        field_name_="max_date",
                    ),
                )
            )
        if min_max_time_fields := self.arguments_type(model, dto_config, "min_max_time"):
            aggregations.extend(
                (
                    FilterFunctionInfo(
                        enum_fields=min_max_time_fields,
                        function="min",
                        aggregation_type="min_max_time",
                        comparison_type=self._inspector.get_type_comparison(time),
                        field_name_="min_time",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_time_fields,
                        function="max",
                        aggregation_type="min_max_time",
                        comparison_type=self._inspector.get_type_comparison(time),
                        field_name_="max_time",
                    ),
                )
            )
        if min_max_string_fields := self.arguments_type(model, dto_config, "min_max_string"):
            aggregations.extend(
                (
                    FilterFunctionInfo(
                        enum_fields=min_max_string_fields,
                        function="min",
                        aggregation_type="min_max_string",
                        comparison_type=self._inspector.get_type_comparison(str),
                        field_name_="min_string",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_string_fields,
                        function="max",
                        aggregation_type="min_max_string",
                        comparison_type=self._inspector.get_type_comparison(str),
                        field_name_="max_string",
                    ),
                )
            )
        return aggregations

    def arguments_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig, aggregation: AggregationType
    ) -> type[EnumDTO] | None:
        try:
            factory = self._type_filtered_factories.get(aggregation)
            if factory is None:
                return None
            dto = factory.enum_factory(model, dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def numeric_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["numeric"]
            dto = factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def min_max_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["min_max"]
            dto = factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def sum_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["sum"]
            dto = factory.factory(model=model, dto_config=dto_config, raise_if_no_fields=True)
        except DTOError:
            return None
        return dto

    def output_functions(self, model: type[DeclarativeBase], dto_config: DTOConfig) -> list[OutputFunctionInfo]:
        int_as_float_config = dto_config.copy_with(
            type_overrides={int: Optional[float], Optional[int]: Optional[float]}
        )
        numeric_fields = self.numeric_field_type(model, int_as_float_config)
        aggregations: list[OutputFunctionInfo] = []

        if self._supports_aggregations("count"):
            aggregations.append(
                OutputFunctionInfo(
                    function="count",
                    require_arguments=False,
                    output_type=Optional[int] if dto_config.partial else int,
                )
            )
        if self._supports_aggregations("sum") and (sum_fields := self.sum_field_type(model, dto_config)):
            aggregations.append(OutputFunctionInfo(function="sum", output_type=sum_fields))
        if self._supports_aggregations("min", "max") and (min_max_fields := self.min_max_field_type(model, dto_config)):
            aggregations.extend(
                [
                    OutputFunctionInfo(function="min", output_type=min_max_fields),
                    OutputFunctionInfo(function="max", output_type=min_max_fields),
                ]
            )

        if numeric_fields:
            aggregations.extend(
                [
                    OutputFunctionInfo(function=function, output_type=numeric_fields)
                    for function in self._statistical_aggregations
                ]
            )
        return sorted(aggregations, key=lambda aggregation: aggregation.function)

    def filter_functions(self, model: type[DeclarativeBase], dto_config: DTOConfig) -> list[FilterFunctionInfo]:
        count_fields = self._count_fields_factory.factory(model=model, dto_config=dto_config)
        numeric_arg_fields = self.arguments_type(model, dto_config, "numeric")
        sum_arg_fields = self.arguments_type(model, dto_config, "sum")

        aggregations: list[FilterFunctionInfo] = []

        if self._supports_aggregations("count"):
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=count_fields,
                    function="count",
                    aggregation_type="numeric",
                    comparison_type=self._inspector.get_type_comparison(int),
                    require_arguments=False,
                )
            )
        if self._supports_aggregations("sum") and sum_arg_fields:
            aggregations.append(
                FilterFunctionInfo(
                    enum_fields=sum_arg_fields,
                    function="sum",
                    aggregation_type="numeric",
                    comparison_type=self._inspector.get_type_comparison(float),
                )
            )

        if self._supports_aggregations("min", "max"):
            aggregations.extend(self._min_max_filters(model, dto_config))

        if numeric_arg_fields:
            comparison = self._inspector.get_type_comparison(float)
            aggregations.extend(
                [
                    FilterFunctionInfo(
                        enum_fields=numeric_arg_fields,
                        function=function,
                        aggregation_type="numeric",
                        comparison_type=comparison,
                    )
                    for function in self._statistical_aggregations
                ]
            )
        return sorted(aggregations, key=lambda aggregation: aggregation.function)
