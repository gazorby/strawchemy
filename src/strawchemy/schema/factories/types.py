from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict, TypeVar, Union

from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument
from strawberry.types.field import StrawberryField
from typing_extensions import Self, Unpack, override

from strawchemy.constants import AGGREGATIONS_KEY, JSON_PATH_KEY, NODES_KEY
from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.base import DTOFactory, DTOFieldDefinition, MappedDTO
from strawchemy.dto.strawberry import (
    AggregateDTO,
    AggregateFieldDefinition,
    DTOKey,
    EnumDTO,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    MappedStrawberryGraphQLDTO,
    OrderByDTO,
)
from strawchemy.dto.types import DTOConfig, DTOMissing, FieldSpec, Purpose, is_fields_iterable
from strawchemy.dto.utils import read_partial, write_all_config
from strawchemy.exceptions import EmptyDTOError
from strawchemy.schema.factories import (
    AggregationInspector,
    EnumFactory,
    GraphQLFactory,
    MappedGraphQLDTOT,
    OrderByFactory,
    StrawchemyMappedFactory,
    UpsertConflictEnumBackend,
)
from strawchemy.schema.field import StrawchemyField
from strawchemy.schema.mutation import (
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
)
from strawchemy.typing import AggregateDTOT, GraphQLDTOT, GraphQLPurpose
from strawchemy.utils.annotation import non_optional_type_hint
from strawchemy.utils.text import snake_to_camel

if TYPE_CHECKING:
    from collections.abc import Generator, Hashable
    from enum import Enum

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, Relation
    from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
    from strawchemy.repository.typing import DeclarativeT
    from strawchemy.schema.factories._kwargs import FactoryMethodKwargs
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.utils.graph import Node

__all__ = (
    "AggregateFieldsFactory",
    "AggregateRootTypeFactory",
    "DistinctOnEnumFactory",
    "MutationInputFactory",
    "ObjectTypeFactory",
    "UpsertConflictEnumFactory",
)

T = TypeVar("T")


class _HasModeKwargs(TypedDict, total=False):
    mode: GraphQLPurpose


class ObjectTypeFactory(StrawchemyMappedFactory[MappedGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[MappedGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_factory: AggregateFieldsFactory[AggregateDTOT] | None = None,
        order_by_factory: OrderByFactory | None = None,
        distinct_on_factory: DistinctOnEnumFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_factory = aggregation_factory or AggregateFieldsFactory(
            mapper, StrawberrryDTOBackend(AggregateDTO)
        )
        self._order_by_factory = order_by_factory or OrderByFactory(
            mapper, handle_cycles=handle_cycles, type_map=type_map
        )
        self._distinct_on_factory = distinct_on_factory or DistinctOnEnumFactory(
            self._mapper, handle_cycles=handle_cycles, type_map=type_map
        )

    def _aggregation_field(
        self, field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition:
        related_model = self.inspector.relation_model(field_def.model_field)
        aggregate_dto_config = dto_config.copy_with(annotation_overrides={})
        dto = self._aggregation_factory.factory(
            model=related_model, dto_config=aggregate_dto_config, parent_field_def=field_def
        )
        return AggregateFieldDefinition(
            dto_config=dto_config,
            model=dto.__dto_model__,
            _model_field=field_def.model_field,
            model_field_name=f"{field_def.name}_aggregate",
            type_hint=dto,
            related_dto=dto,
        )

    def _order_by_input_for_field(self, field: GraphQLFieldDefinition) -> type[OrderByDTO] | None:
        if field.related_model is None:
            return None
        try:
            order_by_input = self._order_by_factory.factory(
                field.related_model, DTOConfig(Purpose.READ, partial=True, include="all"), if_no_fields="raise"
            )
        except EmptyDTOError:
            order_by_input = None
        return order_by_input

    def _distinct_on_input_for_field(self, field: GraphQLFieldDefinition) -> type[EnumDTO] | None:
        if field.related_model is None:
            return None
        try:
            distinct_on_input = self._distinct_on_factory.factory(
                field.related_model, DTOConfig(Purpose.READ, partial=True, include="all"), if_no_fields="raise"
            )
        except EmptyDTOError:
            distinct_on_input = None
        return distinct_on_input

    def _json_field(self) -> StrawberryField:
        return self._mapper.field(
            root_field=False,
            arguments=[
                StrawberryArgument(JSON_PATH_KEY, None, type_annotation=StrawberryAnnotation(annotation=Optional[str]))
            ],
        )

    def _relation_field(
        self,
        field: GraphQLFieldDefinition,
        dto: type[GraphQLDTOT],
        order_config: DTOConfig,
        pagination_config: DTOConfig,
        distinct_on_config: DTOConfig,
        default_pagination: None | DefaultOffsetPagination,
    ) -> tuple[StrawberryField, Any]:
        """Build the pagination/order/distinct_on argument field for a to-many relation."""
        related = Self if field.related_dto is dto else field.related_dto
        type_annotation = list[related] if related is not None else field.type_  # ty: ignore[invalid-type-form]
        assert field.related_model
        order_by_input, distinct_on_input, pagination = None, None, False
        if order_config.is_field_included(field) or self._mapper.config.order_config.is_field_included(field):
            order_by_input = self._order_by_input_for_field(field)
        if pagination_config.is_field_included(field) or self._mapper.config.pagination_config.is_field_included(field):
            pagination = default_pagination or True
        if distinct_on_config.is_field_included(field) or self._mapper.config.distinct_on_config.is_field_included(
            field
        ):
            distinct_on_input = self._distinct_on_input_for_field(field)
        strawberry_field = self._mapper.field(
            pagination=pagination, order_by_input=order_by_input, distinct_on=distinct_on_input, root_field=False
        )
        return strawberry_field, type_annotation

    def _add_fields_arguments(
        self,
        dto: type[GraphQLDTOT],
        base: type[Any] | None,
        order: FieldSpec | None = None,
        paginate: FieldSpec | None = None,
        distinct_on: FieldSpec | None = None,
        default_pagination: None | DefaultOffsetPagination = None,
    ) -> type[GraphQLDTOT]:
        """Add pagination and ordering arguments to a GraphQL DTO type.

        Enhances a GraphQL Data Transfer Object (DTO) type with pagination and ordering
        arguments for relation fields and path filtering for JSON fields. This is a
        post-processing step that modifies the DTO type after initial generation to
        add query capabilities.

        For each relation field with `uselist=True` (one-to-many relationships):
        - If included in the `order` specification: adds an order_by argument
        - If included in the `paginate` specification: adds pagination configuration

        For each JSON field:
        - Adds a `json_path` argument for path-based filtering

        Args:
            dto: The GraphQL DTO type to enhance. Must be a generated strawberry type.
            base: Optional base class whose annotations should be merged into the DTO.
                If provided, annotations from the base class are added to the final DTO.
            order: Field inclusion specification for ordering arguments. Can be:
                - None: No ordering arguments added (default)
                - "all": Add order_by arguments to all relation fields
                - list/set of field names: Add order_by arguments only to named relations
            distinct_on: Field inclusion specification for distinct_on arguments. Can be:
                - None: No distinct_on arguments added (default)
                - "all": Add distinct_on arguments to all relation fields
                - list/set of field names: Add distinct_on arguments only to named relations
            paginate: Field inclusion specification for pagination arguments. Can be:
                - None: No pagination arguments added (default)
                - "all": Add pagination to all relation fields
                - list/set of field names: Add pagination only to named relations
            default_pagination: Default pagination configuration to apply when
                paginate is enabled. If None, uses default pagination (True).

        Returns:
            The modified DTO type with updated __annotations__ and attributes
            containing the new pagination and ordering arguments.
        """
        attributes: dict[str, Any] = {}
        annotations: dict[str, Any] = {}
        order_config = DTOConfig.from_include(order)
        pagination_config = DTOConfig.from_include(paginate)
        distinct_on_config = DTOConfig.from_include(distinct_on)

        # Make sure Class-body `@strawberry.field` resolvers take precedence over auto-derived
        # JSON-path projection and relation arguments. Exclude model_field alias declarations
        # — those are alias mappings, not resolvers, and must keep their annotations.
        body_fields = (
            {
                name
                for name, field_ in inspect.getmembers(base, lambda v: isinstance(v, StrawberryField))
                if not (isinstance(field_, StrawchemyField) and field_.model_field is not None)
            }
            if base is not None
            else set()
        )

        for field in dto.__strawchemy_definition__.field_map.values():
            if field.name in body_fields:
                # Drop the model-derived annotation so the resolver's own return type
                # drives the field type, rather than the column type.
                dto.__annotations__.pop(field.name, None)
                continue
            # Add pagination, distinct_on and ordering arguments for relations
            if field.is_relation and field.uselist:
                attributes[field.name], annotations[field.name] = self._relation_field(
                    field, dto, order_config, pagination_config, distinct_on_config, default_pagination
                )
            # Add path filtering argument for JSON fields
            elif (
                not field.is_relation
                and field.has_model_field
                and self.inspector.model_field_type(field) in {JSON, dict}
            ):
                attributes[field.name] = self._json_field()
                annotations[field.name] = Union[field.type_, None]

        dto.__annotations__ |= annotations
        for name, value in attributes.items():
            setattr(dto, name, value)

        return dto

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None
    ) -> str:
        return f"{base_name}{'Input' if dto_config.purpose is Purpose.WRITE else ''}Type"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        *,
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        field_map = field_map if field_map is not None else {}
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, if_no_fields, field_map=field_map, **kwargs
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[MappedGraphQLDTOT]:
        aggregations = kwargs.get("aggregations", True)
        paginate = kwargs.get("paginate")
        order = kwargs.get("order")
        distinct_on = kwargs.get("distinct_on")
        default_pagination = kwargs.get("default_pagination")
        description = kwargs.get("description")
        directives = kwargs.get("directives", ())
        override_ = kwargs.get("override", False)
        user_defined = kwargs.get("user_defined", False)
        register_type = kwargs.get("register_type", True)
        kwargs["register_type"] = False
        kwargs["aggregations"] = aggregations if dto_config.purpose is Purpose.READ else False
        kwargs["paginate"] = paginate if paginate == "all" else self._mapper.config.pagination
        kwargs["order"] = order if order == "all" else self._mapper.config.order_by
        kwargs["distinct_on"] = distinct_on if distinct_on == "all" else self._mapper.config.distinct_on
        dto = super().factory(model, dto_config, base, name, **kwargs)
        if self.graphql_type(dto_config) == "object":
            dto = self._add_fields_arguments(
                dto,
                base,
                order=order if is_fields_iterable(order) else None,
                distinct_on=distinct_on,
                paginate=paginate,
                default_pagination=default_pagination,
            )
        if register_type:
            return self._mapper.registry.register_type(
                dto,
                graphql_type=self.graphql_type(dto_config),
                dto_config=dto_config,
                description=description,
                directives=directives,
                override=override_,
                user_defined=user_defined,
                default_pagination=default_pagination,
                order=order,
                distinct_on=distinct_on,
                paginate=paginate,
                current_node=kwargs.get("current_node"),
                default_name=self.root_dto_name(model, dto_config),
            )
        return dto


class AggregateRootTypeFactory(ObjectTypeFactory[MappedGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[MappedGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        type_factory: ObjectTypeFactory[MappedGraphQLDTOT] | None = None,
        aggregation_factory: AggregateFieldsFactory[AggregateDTOT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._type_factory = type_factory or ObjectTypeFactory(mapper, backend)
        self._aggregation_factory = aggregation_factory or AggregateFieldsFactory(
            mapper, StrawberrryDTOBackend(AggregateDTO)
        )

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None
    ) -> str:
        return f"{base_name}Root"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        if not node.is_root:
            yield from ()
        key = DTOKey.from_dto_node(node)
        field_map = field_map if field_map is not None else {}
        nodes_dto = self._type_factory.factory(model, dto_config=dto_config, aggregations=aggregations)
        nodes = GraphQLFieldDefinition(
            dto_config=dto_config,
            model=model,
            model_field_name=NODES_KEY,
            type_hint=list[nodes_dto],  # ty: ignore[invalid-type-form]
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[MappedGraphQLDTOT]:
        dto: type[MappedGraphQLDTOT] = super().factory(model, dto_config, base, name, **kwargs)
        dto.__strawchemy_definition__.is_root_aggregation_type = True
        return dto


class AggregateFieldsFactory(GraphQLFactory[AggregateDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[AggregateDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_builder: AggregationInspector | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_builder = aggregation_builder or AggregationInspector(mapper)

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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        node: Node[Relation[Any, AggregateDTOT], None],
        base: type[Any] | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        if_no_fields: Literal["raise", "skip"] = "skip",
        backend_kwargs: dict[str, Any] | None = None,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> type[AggregateDTOT]:
        field_map = field_map if field_map is not None else {}
        model_field = parent_field_def.model_field if parent_field_def else None
        aggregate_config = dto_config.copy_with(partial=True, include="all")
        field_definitions: list[FunctionFieldDefinition] = [
            FunctionFieldDefinition(
                dto_config=dto_config,
                model=model,
                _model_field=model_field if model_field is not None else DTOMissing,
                model_field_name=aggregation.function,
                type_hint=aggregation.output_type,
                _function=aggregation,
                default=aggregation.default,
            )
            for aggregation in self._aggregation_builder.output_functions(model, aggregate_config)
        ]

        root_key = DTOKey.from_dto_node(node)
        field_map.update({root_key + field.model_field_name: field for field in field_definitions})
        return self.backend.build(name, model, field_definitions, **(backend_kwargs or {}))


class DistinctOnEnumFactory(EnumFactory):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}DistinctOnFields"

    @override
    def _resolve_relation_type(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, EnumDTO], None],
        **factory_kwargs: Any,
    ) -> Any:
        return super()._resolve_relation_type(field, dto_config.copy_with(include="all"), node, **factory_kwargs)


class UpsertConflictEnumFactory(EnumFactory):
    inspector: SQLAlchemyGraphQLInspector

    def __init__(
        self,
        mapper: Strawchemy,
        backend: UpsertConflictEnumBackend | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(mapper, backend or UpsertConflictEnumBackend(mapper.config.inspector), handle_cycles, type_map)

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}ConflictFields"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeBase],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, EnumDTO], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        constraints = self.inspector.unique_constraints(model)
        fields = dict(
            self.inspector.field_definitions(
                model,
                dto_config.copy_with(include=[col.key for constraint in constraints for col in constraint.columns]),
            )
        )
        for constraint in constraints:
            field = DTOFieldDefinition(
                dto_config=dto_config,
                model=model,
                model_field_name="_and_".join(fields[column.key].name for column in constraint.columns),
                type_hint=DTOMissing,
                metadata={"constraint": constraint},
            )
            yield GraphQLFieldDefinition.from_field(field)

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, EnumDTO], None],
        has_override: bool,
    ) -> bool:
        constraint_columns = {
            column for constraint in self.inspector.unique_constraints(field.model) for column in constraint.columns
        }
        columns = field.model.__mapper__.column_attrs
        return (
            super().should_exclude_field(field, dto_config, node, has_override)
            or field.model_field_name not in columns
            or any(column not in constraint_columns for column in columns[field.model_field_name].columns)
        )


class MutationInputFactory(ObjectTypeFactory[MappedGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[MappedGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._identifier_input_dto_builder = StrawberrryDTOBackend(MappedStrawberryGraphQLDTO[DeclarativeBase])
        self._identifier_input_dto_factory = DTOFactory(self.inspector, self.backend)
        self._upsert_update_fields_enum_factory = EnumFactory(self._mapper)
        self._upsert_conflict_fields_enum_factory = UpsertConflictEnumFactory(self._mapper)

    def _identifier_input(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
    ) -> type[MappedDTO[Any]]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}IdFieldsInput"
        related_model = field.related_model
        assert related_model
        id_fields = list(self.inspector.id_field_definitions(related_model, write_all_config))
        dto_config = DTOConfig(Purpose.WRITE, include={name for name, _ in id_fields}, exclude_from_scope=True)
        base = self._identifier_input_dto_factory.dtos.get(name)
        if base is None:
            try:
                base = self._identifier_input_dto_factory.factory(
                    related_model, dto_config, name=name, if_no_fields="raise"
                )
            except EmptyDTOError as error:
                msg = (
                    f"Cannot generate `{name}` input type from `{related_model.__name__}` model "
                    "because primary key columns are disabled for write purpose"
                )
                raise EmptyDTOError(msg) from error

        return self._mapper.registry.register_type(
            base, graphql_type="input", dto_config=dto_config, description="Identifier input", user_defined=False
        )

    def _upsert_udpate_fields(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        dto_config: DTOConfig,
    ) -> type[EnumDTO]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}UpdateFields"
        related_model = field.related_model
        assert related_model
        return self._upsert_update_fields_enum_factory.factory(
            related_model,
            dto_config.copy_with(purpose=Purpose.WRITE, include="all"),
            name=name,
            description="Update fields enum",
        )

    def _upsert_conflict_fields(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        dto_config: DTOConfig,
    ) -> type[Enum]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}ConflictFields"
        related_model = field.related_model
        assert related_model
        return self._upsert_conflict_fields_enum_factory.factory(
            related_model,
            dto_config.copy_with(purpose=Purpose.WRITE, include="all"),
            name=name,
            description="Conflict fields enum",
        )

    def _description(self, mode: GraphQLPurpose) -> str:
        if mode == "create_input":
            return "Create input"
        if mode == "update_by_pk_input":
            return "Identifier update input"
        if mode == "update_by_filter_input":
            return "Filter update input"
        return "Input"

    @override
    def _cache_key(
        self,
        model: type[Any],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedGraphQLDTOT], None],
        *,
        mode: GraphQLPurpose,
        **factory_kwargs: Any,
    ) -> Hashable:
        return (
            super()._cache_key(model, dto_config, node, **factory_kwargs),
            node.root.value.model,
            mode,
        )

    @override
    def type_description(self) -> str:
        return "GraphQL input type"

    @override
    def dto_name(
        self,
        base_name: str,
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None,
    ) -> str:
        return f"{node.root.value.model.__name__ if node else ''}{base_name}Input"

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedGraphQLDTOT], None],
        has_override: bool,
    ) -> bool:
        return (
            super().should_exclude_field(field, dto_config, node, has_override)
            or self.inspector.is_foreign_key(field.model_field)
            or self.inspector.relation_cycle(field, node)
        )

    @override
    def _resolve_type(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        dto_config: DTOConfig,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        *,
        mode: GraphQLPurpose,
        **factory_kwargs: Any,
    ) -> Any:
        if not field.is_relation:
            return super()._resolve_basic_type(field, dto_config)
        self._resolve_relation_type(field, dto_config, node, mode=mode, **factory_kwargs)
        identifier_input = self._identifier_input(field, node)
        field_required = self.inspector.required(field.model_field)
        upsert_update_fields = self._upsert_udpate_fields(field, node, dto_config)
        upsert_conflict_fields = self._upsert_conflict_fields(field, node, dto_config)

        if field.uselist:
            if mode == "create_input":
                input_type = ToManyCreateInput[
                    identifier_input,  # ty: ignore[invalid-type-form]
                    field.related_dto,  # ty: ignore[invalid-type-form, invalid-type-arguments]
                    upsert_update_fields,  # ty: ignore[invalid-type-form]
                    upsert_conflict_fields,  # ty: ignore[invalid-type-form]
                ]
            else:
                type_ = (
                    RequiredToManyUpdateInput
                    if self.inspector.reverse_relation_required(field.model_field)
                    else ToManyUpdateInput
                )
                input_type = type_[identifier_input, field.related_dto, upsert_update_fields, upsert_conflict_fields]
        else:
            type_ = RequiredToOneInput if field_required else ToOneInput
            input_type = type_[identifier_input, field.related_dto, upsert_update_fields, upsert_conflict_fields]
        return input_type if field_required and mode == "create_input" else Optional[input_type]

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        if_no_fields: Literal["raise", "skip"] = "skip",
        *,
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **factory_kwargs: Unpack[_HasModeKwargs],
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        mode: GraphQLPurpose = factory_kwargs.pop("mode")
        for field in super().iter_field_definitions(
            name,
            model,
            dto_config,
            base,
            node,
            if_no_fields,
            mode=mode,
            aggregations=aggregations,
            field_map=field_map,
            **factory_kwargs,
        ):
            if mode == "update_by_pk_input" and self.inspector.is_primary_key(field.model_field):
                field.type_ = non_optional_type_hint(field.type_)
            yield field

    @override
    def factory(
        self,
        model: type[DeclarativeT],
        dto_config: DTOConfig = read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        **kwargs: Unpack[FactoryMethodKwargs],
    ) -> type[MappedGraphQLDTOT]:
        mode = kwargs.get("mode")
        assert mode is not None, "InputFactory.factory requires `mode`"
        kwargs["tags"] = kwargs.get("tags") or (set() | {mode})
        kwargs["description"] = kwargs.get("description") or self._description(mode)
        return super().factory(model, dto_config, base, name, **kwargs)
