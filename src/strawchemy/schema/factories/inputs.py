from __future__ import annotations

import dataclasses
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
from strawchemy.schema.filters.fields import FilterFieldMarker
from strawchemy.typing import (
    AggregationFilterFunction,
    ComparisonOperator,
    GraphQLFilterDTOT,
    GraphQLPurpose,
    GraphQLType,
)
from strawchemy.utils.annotation import annotation_name, get_origin_or_self, non_optional_type_hint
from strawchemy.utils.text import snake_to_camel

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Hashable, Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawberry.types.field import StrawberryField

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, ModelFieldT, Relation
    from strawchemy.repository.typing import DeclarativeT
    from strawchemy.schema.factories._kwargs import FactoryMethodKwargs, InputDecoratorKwargs
    from strawchemy.schema.factories.base import TypeScope
    from strawchemy.schema.filters import GraphQLComparison, GraphQLFilter
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
        # `scope` is deliberately dropped: order-by and filter inputs share generated argument types
        # across a schema, so scoping them makes the registry reject the second registration.
        return self._input_wrapper(model=model, name=name, purpose=purpose, mode=mode, **kwargs)

    @staticmethod
    def _declared_strawberry_field(marker: FilterFieldMarker) -> StrawberryField:
        """Builds the strawberry field for a declared filter field from its ``field_kwargs``."""
        return strawberry.field(default=UNSET, **marker.field_kwargs)

    @staticmethod
    def _declared_aggregate_types(base: type[Any] | None) -> dict[str, type[AggregateFilterDTO]]:
        """Extracts ``<relation>_aggregate`` annotations pointing at a declared aggregate filter.

        Returns:
            Mapping of attribute name to the declared aggregate filter type.
        """
        if base is None:
            return {}
        return {
            name: annotation
            for name, annotation in inspect.get_annotations(base, eval_str=True).items()
            if isinstance(annotation, type) and issubclass(annotation, AggregateFilterDTO)
        }

    @staticmethod
    def _validate_marker_context(
        marker: FilterFieldMarker, field_name: str, *, context: Literal["column", "aggregation"]
    ) -> None:
        """Rejects a marker kwarg illegal for the field's declaring context.

        Raises:
            StrawchemyFieldError: If the marker carries a kwarg illegal for ``context``.
        """
        if context == "column" and marker.arguments is not None:
            msg = (
                f"Filter field {field_name!r}: 'arguments' is only valid on aggregation "
                f"function fields, inside a class decorated with aggregate_filter()"
            )
            raise StrawchemyFieldError(msg)
        if context == "aggregation" and (marker.apply is not None or marker.join != "exists"):
            kwarg = "apply" if marker.apply is not None else "join"
            msg = f"Aggregation filter field {field_name!r}: {kwarg!r} is only valid on column filter fields"
            raise StrawchemyFieldError(msg)

    @staticmethod
    def _validate_declared_annotation(annotation: Any, field_name: str, *, data_type: Any, comparison: Any) -> None:
        """Rejects an annotation that names neither the field's data type nor its comparison type.

        The annotation is documentation the factory checks, not a type override. ``None`` means the
        field carries no annotation, which is allowed: a bare marker has nothing to document.

        Raises:
            StrawchemyFieldError: If the annotation names anything else, ``Any`` included.
        """
        if annotation is None:
            return
        # Both sides may arrive subscripted: `comparison` is stored as `OrderComparison[int]`, and
        # the user may write either `OrderComparison` or `OrderComparison[int]`.
        expected_comparison = get_origin_or_self(comparison)
        declared = get_origin_or_self(non_optional_type_hint(annotation))
        if declared is get_origin_or_self(non_optional_type_hint(data_type)) or declared is expected_comparison:
            return
        msg = (
            f"Filter field {field_name!r} is annotated with {annotation_name(annotation)}; annotate it with "
            f"{annotation_name(data_type)} (the value its operators compare) or "
            f"{annotation_name(expected_comparison)} (the comparison input), or drop the annotation"
        )
        raise StrawchemyFieldError(msg)

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
        *,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles=handle_cycles, type_map=type_map, **kwargs)
        self._aggregation_filter_factory = aggregation_filter_factory or AggregateFilterFactory(mapper)

    def _filter_type(self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]) -> type[GraphQLFilter]:
        return self.inspector.get_comparison(field)

    def _aggregation_field(
        self,
        field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        *,
        declared: type[AggregateFilterDTO] | None = None,
    ) -> GraphQLFieldDefinition:
        related_model = self.inspector.relation_model(field_def.model_field)
        if declared is not None:
            if declared.__dto_model__ is not related_model:
                msg = (
                    f"Aggregate filter {declared.__name__!r} targets {declared.__dto_model__.__name__}, "
                    f"but {field_def.name!r} relates to {related_model.__name__}"
                )
                raise StrawchemyFieldError(msg)
            type_hint: type[AggregateFilterDTO] = declared
        else:
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
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        annotation: Any,
        ops: Sequence[ComparisonOperator],
    ) -> type[GraphQLComparison]:
        """Builds the operator-restricted comparison for a declared filter field.

        The comparison shape is derived from the column; the annotation is checked against it by
        :meth:`_validate_column_annotation`.

        Args:
            field: The model column the filter targets.
            annotation: The declared field annotation (scalar or comparison type).
            ops: Selected GraphQL operator names.

        Returns:
            The restricted comparison input type for the column.

        Raises:
            StrawchemyFieldError: If the annotation does not match the column.
        """
        self._validate_column_annotation(field, annotation)
        comparison_cls = self.inspector.get_comparison(field, subscribed=False)
        return comparison_cls.restricted(self.inspector.model_field_type(field), tuple(ops))

    def _validate_column_annotation(
        self, field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], annotation: Any
    ) -> None:
        """Checks a declared column filter field's annotation against its column.

        Args:
            field: The model column the filter targets.
            annotation: The declared field annotation, or ``None``.

        Raises:
            StrawchemyFieldError: If the annotation names neither the column's data type nor its
                comparison type.
        """
        self._validate_declared_annotation(
            annotation,
            field.model_field_name,
            data_type=self.inspector.model_field_type(field),
            comparison=self.inspector.get_comparison(field, subscribed=False),
        )

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

    def _relation_aggregate_field(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        declared_aggregates: dict[str, type[AggregateFilterDTO]],
        matched_aggregates: set[str],
    ) -> GraphQLFieldDefinition:
        """Builds the ``<relation>_aggregate`` field, tracking which declared annotation it matched.

        Args:
            field: The relation field the aggregate attaches to.
            dto_config: Config for the aggregate filter type.
            declared_aggregates: Declared ``<relation>_aggregate`` annotations keyed by attribute name.
            matched_aggregates: Mutated in place with the matched annotation name, if any.

        Returns:
            The ``<relation>_aggregate`` field definition.
        """
        aggregate_name = f"{field.name}_aggregate"
        if aggregate_name in declared_aggregates:
            matched_aggregates.add(aggregate_name)
        return self._aggregation_field(field, dto_config, declared=declared_aggregates.get(aggregate_name))

    def _validate_declared_relations(
        self,
        declared_aggregates: dict[str, type[AggregateFilterDTO]],
        matched: set[str],
        model: type[Any],
        dto_config: DTOConfig,
    ) -> None:
        """Validates that declared ``<relation>_aggregate`` annotations match an emitted relation.

        ``matched`` carries the names that did, collected while the relations were emitted.

        Raises:
            StrawchemyFieldError: If a declared annotation does not map to an emitted relation.
        """
        relations = {name for name, field in self.inspector.field_definitions(model, dto_config) if field.is_relation}
        for field_name in declared_aggregates:
            if field_name in matched:
                continue
            relation_name = field_name.removesuffix("_aggregate")
            reason = (
                f"relation {relation_name!r} is excluded by the filter's include/exclude"
                if relation_name in relations
                else f"{relation_name!r} is not a relation on {model.__name__}"
            )
            msg = f"Filter field {field_name!r} matches no aggregate field: {reason}"
            raise StrawchemyFieldError(msg)

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, GraphQLFilterDTOT], None],
        *,
        if_no_fields: Literal["raise", "skip"] = "skip",
        aggregate_filters: bool = False,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        declared_filters = self.parse_declared_filter_fields(base) if base is not None else {}
        declared_aggregates = self._declared_aggregate_types(base)
        for field_name, (marker, _annotation) in declared_filters.items():
            self._validate_marker_context(marker, field_name, context="column")
        matched_fields: set[str] = set()  # restricted-op declared fields matched to a real column
        matched_aggregates: set[str] = set()  # declared <relation>_aggregate annotations matched to a relation
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, if_no_fields=if_no_fields, **kwargs
        ):
            if field.is_relation:
                field.type_ = Union[field.type_, None]
                if field.uselist and field.related_dto:
                    field.type_ = Union[field.related_dto, None]  # ty: ignore[invalid-type-form]
                if aggregate_filters:
                    yield self._relation_aggregate_field(
                        field,
                        dto_config.copy_with(partial_default=UNSET, partial=True),
                        declared_aggregates,
                        matched_aggregates,
                    )
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
                    self._validate_column_annotation(field, annotation)
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
        self._validate_declared_relations(declared_aggregates, matched_aggregates, model, dto_config)

        yield from self._iter_custom_filter_fields(declared_filters, model, dto_config)

        stripped = set(declared_filters) | set(declared_aggregates)
        if base is not None and stripped:
            # Declared filter fields and declared aggregate annotations supply only a data type
            # or a target type, not a final GraphQL type. Drop their annotations from the base so
            # the strawberry backend does not treat them as verbatim type overrides; the
            # comparison/custom/aggregate types injected above win.
            base.__annotations__ = {
                declared_name: annotation_type
                for declared_name, annotation_type in inspect.get_annotations(base).items()
                if declared_name not in stripped
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
        *,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregate_filter_factory: AggregateFilterFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(BooleanFilterDTO),
            handle_cycles=handle_cycles,
            type_map=type_map,
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
        *,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_builder: AggregationInspector | None = None,
    ) -> None:
        super().__init__(
            mapper, backend or StrawberrryDTOBackend(AggregateFilterDTO), handle_cycles=handle_cycles, type_map=type_map
        )
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

    @override
    def input(
        self,
        model: type[DeclarativeT],
        *,
        name: str | None = None,
        purpose: Purpose = Purpose.READ,
        mode: GraphQLPurpose = "aggregate_filter",
        scope: TypeScope | None = None,
        functions: Sequence[AggregationFilterFunction] | None = None,
        **kwargs: Unpack[InputDecoratorKwargs],
    ) -> Callable[[type[Any]], type[AggregateFilterDTO]]:
        # `_input_wrapper` is called directly: `functions` is not part of `InputDecoratorKwargs`,
        # so routing it through `super().input()` would break the TypedDict contract.
        return self._input_wrapper(
            model=model,
            name=name,
            purpose=purpose,
            mode=mode,
            scope=self._type_scope_to_dto_scope(scope) if scope else None,
            functions=functions,
            **kwargs,
        )

    @override
    def factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO]:
        # `_cache_key` only sees `**factory_kwargs`. Keying on `base` stays local rather than moving
        # into `DTOFactory`: object and filter types are meant to share a cache entry across
        # declarations, aggregate filters are not. `scope_config` is `dto_config` before `_factory`
        # merges `base`'s annotations into it.
        return super().factory(model, dto_config, base, name, declared_base=base, scope_config=dto_config, **kwargs)

    @override
    def _cache_key(
        self,
        model: type[Any],
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateFilterDTO], None],
        *args: Any,
        **factory_kwargs: Any,
    ) -> Hashable:
        return (
            super()._cache_key(model, dto_config, node, *args, **factory_kwargs),
            factory_kwargs.get("declared_base"),
            tuple(sorted(factory_kwargs.get("functions") or ())),
        )

    def _selected_functions(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        declared: dict[str, tuple[FilterFieldMarker, Any]],
        functions: Sequence[AggregationFilterFunction] | None,
    ) -> list[FilterFunctionInfo]:
        """Resolves the aggregation functions the generated input exposes.

        Args:
            model: The model the aggregate filter targets.
            dto_config: Config driving which columns feed the argument enums.
            declared: User-declared fields keyed by aggregation function field name.
            functions: Selected function field names, or ``None`` for every available one.

        Returns:
            The selected functions, in the order the inspector generated them.

        Raises:
            StrawchemyFieldError: If a selected or declared name is not generated for this model, a
                declared field carries a custom ``apply``/non-default ``join``, or no function ends
                up selected.
        """
        available = {
            aggregation.field_name: aggregation
            for aggregation in self.aggregation_builder.filter_functions(model, dto_config)
        }
        for field_name, (marker, _annotation) in declared.items():
            self._validate_marker_context(marker, field_name, context="aggregation")
        unknown = [name for name in (*(functions or ()), *declared) if name not in available]
        if unknown:
            msg = (
                f"Unknown aggregation function(s) {sorted(unknown)} on {model.__name__}; available: {sorted(available)}"
            )
            raise StrawchemyFieldError(msg)
        selected = set(functions) | set(declared) if functions is not None else set(available)
        if not selected:
            msg = f"aggregate_filter() on {model.__name__} selects no aggregation function; select at least one"
            raise StrawchemyFieldError(msg)
        return [aggregation for name, aggregation in available.items() if name in selected]

    def _validate_annotation(self, aggregation: FilterFunctionInfo, annotation: Any) -> None:
        """Checks a declared aggregation function field's annotation against its predicate.

        Args:
            aggregation: The function the declared field refines.
            annotation: The declared field's annotation, or ``None``.

        Raises:
            StrawchemyFieldError: If the annotation names neither the predicate's scalar nor its
                comparison type.
        """
        self._validate_declared_annotation(
            annotation,
            aggregation.field_name,
            data_type=aggregation.comparison_data_type,
            comparison=aggregation.comparison_type,
        )

    def _narrowing_columns(
        self,
        marker: FilterFieldMarker | None,
        aggregation: FilterFunctionInfo,
        scope_config: DTOConfig,
        *,
        declared: bool,
    ) -> Sequence[str] | None:
        """Resolves the columns to narrow one aggregation function's argument enum to.

        An explicit ``arguments=`` marker wins; absent one, a declared filter whose scope restricts
        columns still narrows, so an unmarked function cannot escape its own include/exclude. The
        generated relation aggregate (``declared=False``) has no scope of its own — ``scope_config``
        there is only ambient — so it never narrows.

        Returns:
            The columns to narrow to, or None to keep the shared, unnarrowed enum.
        """
        if marker is not None and marker.arguments is not None:
            return marker.arguments
        if not declared or not self.aggregation_builder.scope_restricts_columns(scope_config):
            return None
        return [
            field.name
            for field in aggregation.enum_fields.__field_definitions__.values()
            if scope_config.is_field_included(field.name)
        ]

    def _aggregate_function_type(
        self,
        model: type[DeclarativeT],
        dto_name: str,
        aggregation: FilterFunctionInfo,
        model_field: type[DTOMissing] | QueryableAttribute[Any],
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None,
        *,
        predicate_type: type[GraphQLComparison] | None = None,
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
                    type_hint=predicate_type or aggregation.comparison_type,
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
        *,
        base: type[Any] | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        if_no_fields: Literal["raise", "skip"] = "skip",
        backend_kwargs: dict[str, Any] | None = None,
        functions: Sequence[AggregationFilterFunction] | None = None,
        scope_config: DTOConfig | None = None,
        **kwargs: Any,
    ) -> type[AggregateFilterDTO]:
        # `dto_config` has had the declared class's attribute names merged into its `include` by
        # now (`DTOConfig.with_base_annotations`); `scope_config` is the pre-merge config, so
        # `arguments=` columns are validated without that noise.
        scope_config = dto_config if scope_config is None else scope_config
        declared = self.parse_declared_filter_fields(base) if base is not None else {}
        requested = set(functions or ()) | set(declared)
        field_defs: list[GraphQLFieldDefinition] = []
        model_field = DTOMissing if parent_field_def is None else parent_field_def.model_field
        for raw_aggregation in self._selected_functions(model, dto_config, declared, functions):
            aggregation = raw_aggregation
            marker, annotation = declared.get(aggregation.field_name, (None, None))
            self._validate_annotation(aggregation, annotation)
            predicate_type = (
                aggregation.comparison_type.restricted(aggregation.comparison_data_type, marker.ops)
                if marker is not None and marker.ops is not None
                else None
            )
            narrowing_columns = self._narrowing_columns(marker, aggregation, scope_config, declared=base is not None)
            if narrowing_columns is not None and not narrowing_columns and aggregation.field_name not in requested:
                # The scope leaves this function no column to aggregate. The user did not ask for it
                # by name, so drop it rather than failing the whole declaration; a function named in
                # `functions=` or carrying a marker still raises in `narrowed_arguments_type`.
                continue
            if narrowing_columns is not None:
                aggregation = dataclasses.replace(
                    aggregation,
                    enum_fields=self.aggregation_builder.narrowed_arguments_type(
                        model, dto_config, aggregation, narrowing_columns, scope_config=scope_config, dto_name=name
                    ),
                )
            type_hint = self._aggregate_function_type(
                model=model,
                dto_name=name,
                parent_field_def=parent_field_def,
                model_field=model_field,
                aggregation=aggregation,
                predicate_type=predicate_type,
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
                    graphql_field=self._declared_strawberry_field(marker) if marker is not None else None,
                ),
            )
        if base is not None and declared:
            base.__annotations__ = {
                declared_name: annotation_type
                for declared_name, annotation_type in inspect.get_annotations(base).items()
                if declared_name not in declared
            }
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
        *,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_filter_factory: AggregateFilterFactory | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or StrawberrryDTOBackend(OrderByDTO),
            handle_cycles=handle_cycles,
            type_map=type_map,
            aggregation_filter_factory=aggregation_filter_factory,
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
        self,
        field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        *,
        declared: type[AggregateFilterDTO] | None = None,
    ) -> GraphQLFieldDefinition:
        # Order-by aggregates are always generated; `declared` only applies to boolean filters.
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
