from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Literal, Optional, TypeVar, Union, cast

import strawberry
from strawberry import UNSET
from typing_extensions import Unpack, override

from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.strawberry import (
    AggregateFieldDefinition,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    BooleanFilterDTO,
    CustomFilterFieldDefinition,
    FilterFunctionInfo,
    FunctionArgFieldDefinition,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
)
from strawchemy.dto.types import DTOConfig, DTOMissing, Purpose
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.factories import AggregationInspector, StrawchemyUnMappedFactory, UnmappedGraphQLDTOT
from strawchemy.schema.filters import GraphQLComparison
from strawchemy.schema.filters.fields import FilterFieldMarker
from strawchemy.typing import AggregationFunction, GraphQLFilterDTOT, GraphQLPurpose, GraphQLType
from strawchemy.utils.annotation import get_origin_or_self
from strawchemy.utils.text import snake_to_camel

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawberry.types.field import StrawberryField

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelFieldT, Relation
    from strawchemy.repository.typing import DeclarativeT
    from strawchemy.schema.factories._kwargs import FactoryMethodKwargs, InputDecoratorKwargs
    from strawchemy.schema.factories.base import TypeScope
    from strawchemy.schema.filters import GraphQLFilter
    from strawchemy.utils.graph import Node

T = TypeVar("T")


class _BaseFilterFactory(StrawchemyUnMappedFactory[UnmappedGraphQLDTOT]):
    @classmethod
    @override
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        return "input"

    @override
    def type_description(self) -> str:
        return "GraphQL Filter Input"

    @override
    def input(
        self,
        model: type[DeclarativeT],
        *,
        name: str | None = None,
        purpose: Purpose = Purpose.READ,
        mode: GraphQLPurpose = "filter",
        scope: TypeScope | None = None,
        **kwargs: Unpack[InputDecoratorKwargs],
    ) -> Callable[[type[Any]], type[UnmappedGraphQLDTOT]]:
        return self._input_wrapper(model=model, name=name, purpose=purpose, mode=mode, **kwargs)

    @staticmethod
    def parse_declared_filter_fields(base: type[Any]) -> dict[str, tuple[FilterFieldMarker, Any]]:
        """Extracts user-declared filter fields from a decorated filter class.

        A declared field is a class attribute whose value is a ``FilterFieldMarker`` (from
        ``strawchemy.filter_field()``). Its annotation supplies the comparison data type.

        Args:
            base: The decorated filter class.

        Returns:
            Mapping of field name to ``(marker, annotation_type)``.

        Raises:
            StrawchemyFieldError: If a restricted (``ops``) or custom (``apply``) field has no annotation.
        """
        # Resolve string annotations (modules using `from __future__ import annotations`).
        annotations = inspect.get_annotations(base, eval_str=True)
        declared: dict[str, tuple[FilterFieldMarker, Any]] = {}
        for name, marker in inspect.getmembers(base, lambda v: isinstance(v, FilterFieldMarker)):
            annotation = annotations.get(name)
            if annotation is None and (marker.ops is not None or marker.apply is not None):
                msg = f"Filter field {name!r} needs a type annotation to determine its data type"
                raise StrawchemyFieldError(msg)
            declared[name] = (marker, annotation)
        return declared


class _FilterFactory(_BaseFilterFactory[GraphQLFilterDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[GraphQLFilterDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_filter_factory = aggregation_filter_factory or AggregateFilterFactory(mapper)

    def _filter_type(self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]) -> type[GraphQLFilter]:
        return self.inspector.get_comparison(field)

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
            type_hint=Optional[type_hint],  # ty: ignore[invalid-type-form]
            default=UNSET,
        )

    @staticmethod
    def _validate_declared_columns(
        declared: dict[str, tuple[FilterFieldMarker, Any]], matched: set[str], model: type[Any]
    ) -> None:
        """Validates that non-custom declared filter fields map to real model columns.

        Restricted (``ops``) and bare declared fields must name an actual column; relationship
        targets and unknown names are out of scope and raise. Custom-apply fields (``apply`` set)
        are virtual and skip this check.

        Args:
            declared: User-declared filter fields keyed by attribute name.
            matched: Names of declared fields that matched a real model column.
            model: The SQLAlchemy model the filter targets.

        Raises:
            StrawchemyFieldError: If a non-custom declared field does not map to a column.
        """
        for field_name, (marker, _annotation) in declared.items():
            if marker.apply is None and field_name not in matched:
                msg = f"Filter field {field_name!r} is not a column on {model.__name__}"
                raise StrawchemyFieldError(msg)

    def _restricted_comparison(
        self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], annotation: Any, ops: Sequence[str]
    ) -> type[GraphQLComparison]:
        """Builds the operator-restricted comparison for a declared filter field.

        The comparison shape is derived from the column; the field annotation is documentary and
        may be the scalar type or a comparison type (e.g. ``TextComparison``) reflecting the shape.

        Args:
            field: The model column the filter targets.
            annotation: The declared field annotation (scalar or comparison type).
            ops: Selected GraphQL operator names.

        Returns:
            The restricted comparison input type for the column.

        Raises:
            StrawchemyFieldError: If a comparison-type annotation does not match the column.
        """
        comparison_cls = self.inspector.get_comparison(field, subscribed=False)
        annotation_origin = get_origin_or_self(annotation)
        if (
            isinstance(annotation_origin, type)
            and issubclass(annotation_origin, GraphQLComparison)
            and annotation_origin is not comparison_cls
        ):
            msg = (
                f"Filter field {field.model_field_name!r} is annotated with "
                f"{annotation_origin.__name__} but its column resolves to {comparison_cls.__name__}"
            )
            raise StrawchemyFieldError(msg)
        return comparison_cls.restricted(self.inspector.model_field_type(field), tuple(ops))

    def _iter_custom_filter_fields(
        self,
        declared_filters: dict[str, tuple[FilterFieldMarker, Any]],
        model: type[DeclarativeT],
        dto_config: DTOConfig,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        """Yields custom-apply virtual filter fields (those declared with ``apply``).

        These are not backed by a model column; each becomes a ``CustomFilterFieldDefinition``
        whose value the transpiler folds into the query via the callable.
        """
        for field_name, (declared_filter, annotation) in declared_filters.items():
            if declared_filter.apply is None:
                continue
            custom_field = CustomFilterFieldDefinition(
                dto_config=dto_config,
                model=model,
                model_field_name=field_name,
                type_hint=Optional[annotation],
                apply=declared_filter.apply,
                join=declared_filter.join,
                graphql_field=self._declared_strawberry_field(declared_filter),
                default=UNSET,
                default_factory=DTOMissing,
            )
            yield custom_field

    @staticmethod
    def _declared_strawberry_field(marker: FilterFieldMarker) -> StrawberryField:
        """Builds the strawberry field for a declared filter field from its ``field_kwargs``."""
        return strawberry.field(default=UNSET, **marker.field_kwargs)

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, GraphQLFilterDTOT], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        *,
        aggregate_filters: bool = False,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        declared_filters = self.parse_declared_filter_fields(base) if base is not None else {}
        matched_fields: set[str] = set()  # restricted-op declared fields matched to a real column
        for field in super().iter_field_definitions(name, model, dto_config, base, node, if_no_fields, **kwargs):
            if field.is_relation:
                field.type_ = Union[field.type_, None]
                if field.uselist and field.related_dto:
                    field.type_ = Union[field.related_dto, None]  # ty: ignore[invalid-type-form]
                if aggregate_filters:
                    yield self._aggregation_field(field, dto_config.copy_with(partial_default=UNSET, partial=True))
            else:
                declared_entry = declared_filters.get(field.model_field_name)
                declared_filter = declared_entry[0] if declared_entry is not None else None
                annotation = declared_entry[1] if declared_entry is not None else None
                if declared_filter is not None and declared_filter.apply is not None:
                    # Custom-apply field overrides this real column; skip the default
                    # comparison and let the injection loop below emit the custom field once.
                    continue
                if declared_filter is not None and declared_filter.ops is not None:
                    comparison_type = self._restricted_comparison(field, annotation, declared_filter.ops)
                    matched_fields.add(field.model_field_name)
                elif declared_filter is not None:
                    # bare filter_field(): force-include this column's full default comparison
                    comparison_type = self._filter_type(field)
                    matched_fields.add(field.model_field_name)
                else:
                    comparison_type = self._filter_type(field)
                field.type_ = Optional[comparison_type]  # ty: ignore[invalid-type-form]
                if declared_filter is not None:
                    # super() yields GraphQLFieldDefinition (carries graphql_field), though typed as the base.
                    cast("GraphQLFieldDefinition", field).graphql_field = self._declared_strawberry_field(
                        declared_filter
                    )

            field.default = UNSET
            field.default_factory = DTOMissing
            yield field

        self._validate_declared_columns(declared_filters, matched_fields, model)

        yield from self._iter_custom_filter_fields(declared_filters, model, dto_config)

        if base is not None and declared_filters:
            # Declared filter fields supply only a data type, not a final GraphQL type.
            # Drop their annotations from the base so the strawberry backend does not treat
            # them as verbatim type overrides; the comparison/custom types injected above win.
            base.__annotations__ = {
                annotation_name: annotation_type
                for annotation_name, annotation_type in inspect.get_annotations(base).items()
                if annotation_name not in declared_filters
            }

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
        *,
        aggregate_filters: bool = True,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[GraphQLFilterDTOT]:
        return super().factory(model, dto_config, base, name, aggregate_filters=aggregate_filters, **kwargs)


class BooleanFilterFactory(_FilterFactory[BooleanFilterDTO]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[BooleanFilterDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregate_filter_factory: AggregateFilterFactory | None = None,
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

    @override
    def type_description(self) -> str:
        return "Boolean expression to compare fields. All fields are combined with logical 'AND'."


class AggregateFilterFactory(_BaseFilterFactory[AggregateFilterDTO]):
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
        model_field: type[DTOMissing] | QueryableAttribute[Any],
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
                    type_hint=list[aggregation.enum_fields]  # ty: ignore[invalid-type-form]
                    if aggregation.require_arguments
                    else Optional[list[aggregation.enum_fields]],  # ty: ignore[invalid-type-form]
                    default_factory=DTOMissing if aggregation.require_arguments else list,
                    _function=aggregation,
                    _model_field=model_field,
                ),
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name="distinct",
                    type_hint=Optional[bool],
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
        dto.__strawchemy_definition__.description = "Field filtering information"
        dto.__dto_function_info__ = aggregation
        return self._mapper.registry.register_type(
            dto,
            dto_config=dto_config,
            graphql_type="input",
            default_name=self.root_dto_name(model, dto_config),
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
        if_no_fields: Literal["raise", "skip"] = "skip",
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO]:
        function_aliases: dict[str, AggregationFunction] = {}
        field_defs: list[GraphQLFieldDefinition] = []
        model_field = DTOMissing if parent_field_def is None else parent_field_def.model_field
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
                    type_hint=Optional[type_hint],  # ty: ignore[invalid-type-form]
                    default=UNSET,
                    _model_field=model_field,
                    _function=aggregation,
                ),
            )
        dto = self.backend.build(name, model, field_defs, base, **(backend_kwargs or {}))
        dto.__strawchemy_definition__.description = (
            "Boolean expression to compare field aggregations. All fields are combined with logical 'AND'."
        )
        return dto


class OrderByFactory(_FilterFactory[OrderByDTO]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[OrderByDTO] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterFactory | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(OrderByDTO),
            handle_cycles,
            type_map,
            aggregation_filter_factory,
        )

    @override
    def type_description(self) -> str:
        return "Ordering input."

    @override
    def _filter_type(self, field: DTOFieldDefinition[T, ModelFieldT]) -> type[OrderByEnum]:
        return OrderByEnum

    def _order_by_aggregation_fields(
        self, aggregation: FilterFunctionInfo, model: type[Any], dto_config: DTOConfig
    ) -> type[OrderByDTO]:
        model_fields = {field.name: field for _, field in self.inspector.field_definitions(model, dto_config)}
        field_defs = [
            FunctionArgFieldDefinition(
                dto_config=dto_config,
                model=model,
                model_field_name=name.field_definition.name,
                type_hint=OrderByEnum,
                _function=aggregation,
                _model_field=model_fields[name.field_definition.name].model_field,
            )
            for name in aggregation.enum_fields
        ]

        name = f"{model.__name__}Aggregate{snake_to_camel(aggregation.aggregation_type)}FieldsOrderBy"
        dto = self.backend.build(name, model, field_defs)
        return self._mapper.registry.register_type(
            dto,
            dto_config=dto_config,
            graphql_type="input",
            default_name=self.root_dto_name(model, dto_config),
        )

    def _order_by_aggregation(self, model: type[DeclarativeBase], dto_config: DTOConfig) -> type[OrderByDTO]:
        field_definitions: list[GraphQLFieldDefinition] = []
        for aggregation in self._aggregation_filter_factory.aggregation_builder.filter_functions(model, dto_config):
            if aggregation.require_arguments:
                type_hint = self._order_by_aggregation_fields(aggregation, model, dto_config)
            else:
                type_hint = OrderByEnum
            dto_config = DTOConfig(
                dto_config.purpose,
                aliases={aggregation.function: aggregation.field_name},
                partial=dto_config.partial,
                partial_default=UNSET,
            )
            field_definitions.append(
                FunctionFieldDefinition(
                    dto_config=dto_config,
                    model=model,
                    model_field_name=aggregation.field_name,
                    type_hint=Optional[type_hint],  # ty: ignore[invalid-type-form]
                    default=UNSET,
                    _function=aggregation,
                )
            )

        dto = self.backend.build(f"{model.__name__}AggregateOrderBy", model, field_definitions)
        return self._mapper.registry.register_type(
            dto,
            dto_config=dto_config,
            graphql_type="input",
            default_name=self.root_dto_name(model, dto_config),
        )

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
            type_hint=Optional[self._order_by_aggregation(related_model, dto_config)],  # ty: ignore[invalid-type-form]
            default=UNSET,
        )

    @override
    def _resolve_relation_type(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, OrderByDTO], None],
        **factory_kwargs: Any,
    ) -> Any:
        return super()._resolve_relation_type(field, dto_config.copy_with(include="all"), node, **factory_kwargs)

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
        *,
        aggregate_filters: bool = True,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[OrderByDTO]:
        dto = super().factory(model, dto_config, base, name, aggregate_filters=aggregate_filters, **kwargs)
        dto.__strawchemy_definition__.description = "Ordering options"
        return dto
