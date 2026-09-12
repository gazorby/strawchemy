from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, TypeVar, cast

from sqlalchemy.orm import DeclarativeBase
from typing_extensions import Unpack, override

from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.strawberry import (
    EnumDTO,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    OutputFunctionInfo,
    UnmappedStrawberryGraphQLDTO,
)
from strawchemy.dto.types import FieldGroup
from strawchemy.exceptions import DTOError, StrawchemyFieldError
from strawchemy.schema.factories.base import GraphQLFactory
from strawchemy.schema.factories.enum import EnumBackend, EnumFactory
from strawchemy.utils.text import snake_to_camel

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from sqlalchemy.orm import QueryableAttribute

    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelT, Relation
    from strawchemy.dto.types import DTOConfig
    from strawchemy.mapper import Strawchemy
    from strawchemy.repository.typing import DeclarativeT
    from strawchemy.schema.factories._kwargs import FactoryMethodKwargs
    from strawchemy.typing import AggregationFunction, AggregationType, FunctionInfo
    from strawchemy.utils.graph import Node

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


class _CountFieldsFactory(EnumFactory):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}CountFields"


class _FunctionArgFactory(GraphQLFactory[UnmappedStrawberryGraphQLDTO[DeclarativeBase]]):
    types: ClassVar[set[type[Any]]] = set()

    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None = None,
        *,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(UnmappedStrawberryGraphQLDTO),
            handle_cycles=handle_cycles,
            type_map=type_map,
        )
        self._enum_backend = EnumBackend()

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
        *,
        if_no_fields: Literal["raise", "skip"] = "skip",
        function: FunctionInfo | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        for field_def in super().iter_field_definitions(
            name, model, dto_config, base, node, if_no_fields=if_no_fields, **kwargs
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
        *,
        function: FunctionInfo | None = None,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]]:
        return super().factory(model, dto_config, base, name, function=function, **kwargs)

    def enum_factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        name: str | None = None,
        base: type[Any] | None = None,
        if_no_fields: Literal["raise", "skip"] = "skip",
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
            if_no_fields=if_no_fields,
            **kwargs,
        )
        return self._enum_backend.build(name, model, list(field_defs), base)


class _TypeFilteredFunctionArgFactory(_FunctionArgFactory):
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
            super(_FunctionArgFactory, self).should_exclude_field(field, dto_config, node, has_override)
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
        self._count_fields_factory = _CountFieldsFactory(mapper)

        # Create type-filtered factories from configuration
        self._type_filtered_factories: dict[str, _TypeFilteredFunctionArgFactory] = {
            key: _TypeFilteredFunctionArgFactory(mapper, config)
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
                        comparison_data_type=float,
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_numeric_fields,
                        function="max",
                        aggregation_type="numeric",
                        comparison_type=self._inspector.get_type_comparison(float),
                        comparison_data_type=float,
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
                        comparison_data_type=datetime,
                        field_name_="min_datetime",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_datetime_fields,
                        function="max",
                        aggregation_type="min_max_datetime",
                        comparison_type=self._inspector.get_type_comparison(datetime),
                        comparison_data_type=datetime,
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
                        comparison_data_type=date,
                        field_name_="min_date",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_date_fields,
                        function="max",
                        aggregation_type="min_max_date",
                        comparison_type=self._inspector.get_type_comparison(date),
                        comparison_data_type=date,
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
                        comparison_data_type=time,
                        field_name_="min_time",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_time_fields,
                        function="max",
                        aggregation_type="min_max_time",
                        comparison_type=self._inspector.get_type_comparison(time),
                        comparison_data_type=time,
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
                        comparison_data_type=str,
                        field_name_="min_string",
                    ),
                    FilterFunctionInfo(
                        enum_fields=min_max_string_fields,
                        function="max",
                        aggregation_type="min_max_string",
                        comparison_type=self._inspector.get_type_comparison(str),
                        comparison_data_type=str,
                        field_name_="max_string",
                    ),
                )
            )
        return aggregations

    def arguments_type(
        self,
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
        aggregation: AggregationType,
        *,
        name: str | None = None,
    ) -> type[EnumDTO] | None:
        try:
            factory = self._type_filtered_factories.get(aggregation)
            if factory is None:
                return None
            dto = factory.enum_factory(model, dto_config, name=name, if_no_fields="raise")
        except DTOError:
            return None
        return dto

    @staticmethod
    def _validate_columns_in_scope(
        scope_config: DTOConfig,
        model: type[DeclarativeBase],
        aggregation: FilterFunctionInfo,
        columns: Sequence[str],
    ) -> None:
        """Rejects columns the enclosing decorator's include/exclude already puts out of scope.

        ``scope_config`` is the enclosing aggregate filter's user-supplied config captured before
        ``DTOConfig.with_base_annotations`` merges the declared class's own attribute names into
        ``include`` (those attributes are aggregation *function* names, e.g. ``count``, not model
        columns, so checking against the post-merge config would misattribute a real column that
        happens to share a function's name). A ``scope_config`` with no restriction at all (bare,
        no ``include``/``exclude`` given) imposes nothing here -- only an explicit
        ``include``/``exclude`` on the enclosing decorator narrows the columns ``arguments=`` may
        name.

        Args:
            scope_config: The enclosing aggregate filter's config, from before base-class
                annotations were merged into it.
            model: The model being aggregated.
            aggregation: The function whose arguments are narrowed.
            columns: Selected column names.

        Raises:
            StrawchemyFieldError: If a column falls outside the enclosing include/exclude.
        """
        if not scope_config.included_fields and not scope_config.excluded_fields:
            return
        outside = sorted(column for column in columns if not scope_config.is_field_included(column))
        if outside:
            msg = (
                f"Column(s) {outside} are excluded by {model.__name__}'s aggregate filter "
                f"include/exclude and cannot be selected by {aggregation.field_name!r}'s arguments"
            )
            raise StrawchemyFieldError(msg)

    @staticmethod
    def scope_restricts_columns(scope_config: DTOConfig) -> bool:
        """Whether the declaring aggregate filter's include/exclude actually narrows columns.

        True for an explicit ``include`` other than the "all" field group, or any ``exclude``;
        false for a bare decorator or an explicit ``include="all"``, both of which leave every
        function free to aggregate over every model column.

        Args:
            scope_config: The enclosing aggregate filter's user-supplied config, from before
                base-class annotations were merged into it.

        Returns:
            True if the scope narrows which columns can be aggregated.
        """
        if scope_config.excluded_fields:
            return True
        included = scope_config.included_fields
        return bool(included) and FieldGroup.ALL not in included.field_set

    def narrowed_arguments_type(
        self,
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
        aggregation: FilterFunctionInfo,
        columns: Sequence[str],
        *,
        scope_config: DTOConfig,
        dto_name: str,
    ) -> type[EnumDTO]:
        """Builds the argument enum of one aggregation function, limited to ``columns``.

        ``scope_config`` predates the merge of base-class annotations into ``dto_config``, so
        ``columns`` is validated without the declared attribute names as noise. ``dto_name`` scopes
        the enum's own name away from the shared, unnarrowed enum and from another class narrowing
        the same function.

        Returns:
            An enum named ``{dto_name}{Function}FieldsEnum`` holding only the selected columns.

        Raises:
            StrawchemyFieldError: If a column is unknown, excluded by the enclosing decorator, or
                cannot be aggregated by this function.
        """
        self._validate_columns_in_scope(scope_config, model, aggregation, columns)
        narrowed = dto_config.copy_with(include=set(columns))
        name = f"{dto_name}{snake_to_camel(aggregation.field_name).capitalize()}FieldsEnum"
        if aggregation.function == "count":
            # `_count_fields_factory.factory` goes through the shared DTO cache, whose cache key
            # conflates `include`/`exclude` (see `DTOFactory._root_cache_key`); `no_cache=True`
            # keeps this narrowed, per-function build from reading back an unrelated dto that
            # happens to collide on that key.
            dto = self._count_fields_factory.factory(model=model, dto_config=narrowed, name=name, no_cache=True)
        else:
            # `sum`'s own `FilterFunctionInfo.aggregation_type` is "numeric" (matching its float
            # comparison), but its *candidate columns* are built from the wider "sum" type filter
            # (which also allows `str`/`timedelta`); narrowing must use that same wider filter, not
            # the comparison-oriented "numeric" one, or a legitimately narrowed str/timedelta column
            # gets wrongly rejected.
            type_filter = "sum" if aggregation.function == "sum" else aggregation.aggregation_type
            dto = self.arguments_type(model, narrowed, type_filter, name=name)
        kept = {field.name for field in dto.__field_definitions__.values()} if dto is not None else set()
        missing = sorted(set(columns) - kept)
        if not kept and not missing:
            # `columns` came out empty, so nothing is "missing" and the specific error below cannot
            # fire. An empty enum is invalid GraphQL, and building it would defer the failure to
            # schema construction with nothing pointing back at the declaration.
            msg = (
                f"{aggregation.field_name!r} on {model.__name__} has no column left to aggregate; "
                f"the aggregate filter's include/exclude leaves it no candidate column"
            )
            raise StrawchemyFieldError(msg)
        if dto is None or missing:
            msg = (
                f"Column(s) {missing or sorted(columns)} cannot be aggregated by "
                f"{aggregation.field_name!r} on {model.__name__}; "
                f"check the column exists and its type is supported by this function"
            )
            raise StrawchemyFieldError(msg)
        return dto

    def numeric_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["numeric"]
            dto = factory.factory(model=model, dto_config=dto_config, if_no_fields="raise")
        except DTOError:
            return None
        return dto

    def min_max_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["min_max"]
            dto = factory.factory(model=model, dto_config=dto_config, if_no_fields="raise")
        except DTOError:
            return None
        return dto

    def sum_field_type(
        self, model: type[DeclarativeBase], dto_config: DTOConfig
    ) -> type[UnmappedStrawberryGraphQLDTO[DeclarativeBase]] | None:
        try:
            factory = self._type_filtered_factories["sum"]
            dto = factory.factory(model=model, dto_config=dto_config, if_no_fields="raise")
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
                    comparison_data_type=int,
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
                    comparison_data_type=float,
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
                        comparison_data_type=float,
                    )
                    for function in self._statistical_aggregations
                ]
            )
        return sorted(aggregations, key=lambda aggregation: aggregation.function)
