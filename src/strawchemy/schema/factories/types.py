from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union

from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument
from typing_extensions import Self, override

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
)
from strawchemy.dto.types import DTOConfig, DTOMissing, IncludeFields, Purpose
from strawchemy.dto.utils import read_all_partial_config, read_partial, write_all_config
from strawchemy.exceptions import EmptyDTOError
from strawchemy.schema.factories import (
    AggregationInspector,
    EnumDTOFactory,
    GraphQLDTOFactory,
    MappedGraphQLDTOT,
    OrderByDTOFactory,
    StrawchemyMappedFactory,
    UpsertConflictFieldsEnumDTOBackend,
)
from strawchemy.schema.mutation import (
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
)
from strawchemy.typing import AggregateDTOT, GraphQLDTOT, GraphQLPurpose
from strawchemy.utils.annotation import get_annotations, non_optional_type_hint
from strawchemy.utils.text import snake_to_camel

if TYPE_CHECKING:
    from collections.abc import Generator, Hashable, Sequence
    from enum import Enum

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, Relation
    from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
    from strawchemy.repository.typing import DeclarativeT
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.utils.graph import Node


__all__ = (
    "AggregateDTOFactory",
    "DistinctOnFieldsDTOFactory",
    "InputFactory",
    "RootAggregateTypeDTOFactory",
    "TypeDTOFactory",
    "UpsertConflictFieldsDTOFactory",
)

T = TypeVar("T")


class TypeDTOFactory(StrawchemyMappedFactory[MappedGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[MappedGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregation_factory: AggregateDTOFactory[AggregateDTOT] | None = None,
        order_by_factory: OrderByDTOFactory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._aggregation_factory = aggregation_factory or AggregateDTOFactory(
            mapper, StrawberrryDTOBackend(AggregateDTO)
        )
        self._order_by_factory = order_by_factory or OrderByDTOFactory(
            mapper, handle_cycles=handle_cycles, type_map=type_map
        )

    def _aggregation_field(
        self, field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]], dto_config: DTOConfig
    ) -> GraphQLFieldDefinition:
        """
        Create an aggregation field definition for a to-many relation field.
        
        Parameters:
            field_def (DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]): Field definition for the relation to aggregate.
            dto_config (DTOConfig): DTO configuration used for the aggregation field (inherits base config with no annotation overrides).
        
        Returns:
            GraphQLFieldDefinition: An AggregateFieldDefinition describing the related model's aggregation DTO and linking it to the original relation field.
        """
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

    def _add_fields_arguments(
        self,
        dto: type[GraphQLDTOT],
        base: type[Any] | None,
        order: IncludeFields | None = None,
        paginate: IncludeFields | None = None,
        default_pagination: None | DefaultOffsetPagination = None,
    ) -> type[GraphQLDTOT]:
        """
        Augments a generated DTO type by adding per-field pagination, ordering, and JSON-path filter arguments.
        
        This mutates the provided DTO class by adding Strawberry field attributes and updating its __annotations__:
        - For to-many relation fields, adds ordering and/or pagination arguments when included according to the provided IncludeFields values; `order` controls whether an order-by input is attached, `paginate` controls whether pagination is enabled, and `default_pagination` supplies a default pagination configuration when pagination is enabled.
        - For non-relation JSON/dict-backed model fields, adds a `JSON_PATH_KEY` string argument to support path-based filtering.
        - If `base` is provided, copies annotations and any attributes present on `base` onto the DTO.
        
        Parameters:
            dto: The GraphQL DTO class to augment.
            base: Optional base DTO class whose annotations and attributes should be merged onto `dto`.
            order: IncludeFields controlling which relation fields receive an order-by argument.
            paginate: IncludeFields controlling which relation fields receive pagination.
            default_pagination: Optional default pagination configuration to apply when pagination is enabled for a field.
        
        Returns:
            The same DTO class passed in, after augmentation.
        """
        attributes: dict[str, Any] = {}
        annotations: dict[str, Any] = {}
        order_config = DTOConfig.from_include(order)
        paginate_config = DTOConfig.from_include(paginate)

        for field in dto.__strawchemy_field_map__.values():
            # Add pagination and ordering arguments for relations
            if field.is_relation and field.uselist:
                related = Self if field.related_dto is dto else field.related_dto
                type_annotation = list[related] if related is not None else field.type_
                assert field.related_model
                order_by_input, pagination = None, False
                if order_config.is_field_included(field.model_field_name):
                    order_by_input = self._order_by_factory.factory(field.related_model, read_all_partial_config)
                if paginate_config.is_field_included(field.model_field_name):
                    pagination = default_pagination or True
                strawberry_field = self._mapper.field(pagination=pagination, order_by=order_by_input, root_field=False)
                attributes[field.name] = strawberry_field
                annotations[field.name] = type_annotation
            # Add path filtering argument for JSON fields
            elif (
                not field.is_relation
                and field.has_model_field
                and self.inspector.model_field_type(field) in {JSON, dict}
            ):
                attributes[field.name] = self._mapper.field(
                    root_field=False,
                    arguments=[
                        StrawberryArgument(
                            JSON_PATH_KEY, None, type_annotation=StrawberryAnnotation(annotation=Optional[str])
                        )
                    ],
                )
                annotations[field.name] = Union[field.type_, None]

        dto.__annotations__ |= annotations
        for name, value in attributes.items():
            setattr(dto, name, value)

        if base:
            dto.__annotations__ |= get_annotations(base)
            for name, value in get_annotations(base).items():
                if not hasattr(base, name):
                    continue
                setattr(dto, name, value)
        return dto

    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None
    ) -> str:
        """
        Builds a GraphQL DTO type name, appending "Input" for write-purpose DTOs.
        
        Parameters:
            base_name (str): Base name for the DTO (e.g., model or field base).
            dto_config (DTOConfig): Controls the DTO purpose; if its purpose is Purpose.WRITE the returned name will include "Input" before the "Type" suffix.
            node (optional): Optional node context; not used to determine the name.
        
        Returns:
            str: The constructed DTO type name (for example "UserInputType" or "UserType").
        """
        return f"{base_name}{'Input' if dto_config.purpose is Purpose.WRITE else ''}Type"

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        aggregations: bool = False,
        field_map: dict[DTOKey, GraphQLFieldDefinition] | None = None,
        **kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        default_pagination: None | DefaultOffsetPagination = None,
        order: IncludeFields | None = None,
        paginate: IncludeFields | None = None,
        aggregations: bool = True,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
        register_type: bool = True,
        **kwargs: Any,
    ) -> type[MappedGraphQLDTOT]:
        """
        Create or retrieve a GraphQL DTO type for the given SQLAlchemy model with optional relation argument augmentation.
        
        Parameters:
            model (type[DeclarativeT]): The SQLAlchemy mapped model to build the DTO for.
            dto_config (DTOConfig): Configuration that controls how the DTO is built (purpose, included fields, etc.).
            base (type | None): An optional base DTO type to inherit fields from.
            name (str | None): Explicit name to use for the generated DTO type.
            parent_field_def (DTOFieldDefinition | None): Field definition from a parent used when generating nested types.
            current_node (Node | None): Relation graph node representing the current position in relation traversal.
            raise_if_no_fields (bool): If true, raise an error when no fields are produced for the DTO.
            tags (set[str] | None): Optional tags to attach to the created DTO.
            backend_kwargs (dict | None): Backend-specific keyword arguments forwarded to the underlying builder.
            default_pagination (DefaultOffsetPagination | None): Default pagination configuration to apply to relation fields when applicable.
            order (IncludeFields | None): Controls whether ordering inputs are included for relation fields; typically "all" to enable.
            paginate (IncludeFields | None): Controls whether pagination inputs are included for relation fields; typically "all" to enable.
            aggregations (bool): Whether aggregation fields should be generated for to-many relations (only applied for READ purpose).
            description (str | None): Optional description to register with the GraphQL type.
            directives (Sequence[object] | None): Optional GraphQL directives to register with the type.
            override (bool): If true, allow overriding an existing registered type with the same name.
            user_defined (bool): Marks the registered type as user-defined when True.
            register_type (bool): If true, register the resulting GraphQL type with the backend/registry before returning it.
            **kwargs: Additional options forwarded to the underlying factory.
        
        Returns:
            type[MappedGraphQLDTOT]: A GraphQL DTO type class for the provided model; if register_type is True, the returned type is registered with the system.
        """
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags,
            backend_kwargs,
            aggregations=aggregations if dto_config.purpose is Purpose.READ else False,
            register_type=False,
            override=override,
            paginate=paginate if paginate == "all" else None,
            order=order if order == "all" else None,
            default_pagination=default_pagination,
            **kwargs,
        )
        if self.graphql_type(dto_config) == "object":
            dto = self._add_fields_arguments(
                dto, base, default_pagination=default_pagination, order=order, paginate=paginate
            )
        if register_type:
            return self._register_type(
                dto,
                dto_config=dto_config,
                description=description,
                directives=directives,
                override=override,
                user_defined=user_defined,
                default_pagination=default_pagination,
                order=order,
                paginate=paginate,
                current_node=current_node,
            )
        return dto


class RootAggregateTypeDTOFactory(TypeDTOFactory[MappedGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy,
        backend: DTOBackend[MappedGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        type_factory: TypeDTOFactory[MappedGraphQLDTOT] | None = None,
        aggregation_factory: AggregateDTOFactory[AggregateDTOT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._type_factory = type_factory or TypeDTOFactory(mapper, backend)
        self._aggregation_factory = aggregation_factory or AggregateDTOFactory(
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
        raise_if_no_fields: bool = False,
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
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregations: bool = True,
        **kwargs: Any,
    ) -> type[MappedGraphQLDTOT]:
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags,
            backend_kwargs,
            aggregations=aggregations,
            **kwargs,
        )
        dto.__strawchemy_is_root_aggregation_type__ = True
        return dto


class AggregateDTOFactory(GraphQLDTOFactory[AggregateDTOT]):
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
        raise_if_no_fields: bool = False,
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


class DistinctOnFieldsDTOFactory(EnumDTOFactory):
    @override
    def dto_name(
        self, base_name: str, dto_config: DTOConfig, node: Node[Relation[Any, EnumDTO], None] | None = None
    ) -> str:
        return f"{base_name}DistinctOnFields"


class UpsertConflictFieldsDTOFactory(EnumDTOFactory):
    inspector: SQLAlchemyGraphQLInspector

    def __init__(
        self,
        inspector: SQLAlchemyGraphQLInspector,
        backend: UpsertConflictFieldsEnumDTOBackend | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(inspector, backend or UpsertConflictFieldsEnumDTOBackend(inspector), handle_cycles, type_map)

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
        raise_if_no_fields: bool = False,
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


class InputFactory(TypeDTOFactory[MappedGraphQLDTOT]):
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
        self._upsert_update_fields_enum_factory = EnumDTOFactory(self.inspector)
        self._upsert_conflict_fields_enum_factory = UpsertConflictFieldsDTOFactory(self.inspector)

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
                    related_model, dto_config, name=name, raise_if_no_fields=True
                )
            except EmptyDTOError as error:
                msg = (
                    f"Cannot generate `{name}` input type from `{related_model.__name__}` model "
                    "because primary key columns are disabled for write purpose"
                )
                raise EmptyDTOError(msg) from error

        return self._register_type(base, dto_config, node, description="Identifier input", user_defined=False)

    def _upsert_udpate_fields(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        dto_config: DTOConfig,
    ) -> type[EnumDTO]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}UpdateFields"
        related_model = field.related_model
        assert related_model
        update_fields = self._upsert_update_fields_enum_factory.factory(
            related_model, dto_config.copy_with(purpose=Purpose.WRITE, include="all"), name=name
        )
        return self._mapper.registry.register_enum(update_fields, name=name, description="Update fields enum")

    def _upsert_conflict_fields(
        self,
        field: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]],
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        dto_config: DTOConfig,
    ) -> type[Enum]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}ConflictFields"
        related_model = field.related_model
        assert related_model
        conflict_fields = self._upsert_conflict_fields_enum_factory.factory(
            related_model, dto_config.copy_with(purpose=Purpose.WRITE, include="all"), name=name
        )
        return self._mapper.registry.register_enum(conflict_fields, name=name, description="Conflict fields enum")

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
        """
        Compose a cache key that uniquely identifies this factory configuration.
        
        Parameters:
            mode (GraphQLPurpose): The GraphQL purpose (e.g., READ, WRITE) influencing the key.
        
        Returns:
            hashable: A hashable value combining the base factory cache key, the root model from `node`, and `mode`.
        """
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
                    identifier_input, field.related_dto, upsert_update_fields, upsert_conflict_fields  # pyright: ignore[reportInvalidTypeArguments]
                ]
            else:
                type_ = (
                    RequiredToManyUpdateInput
                    if self.inspector.reverse_relation_required(field.model_field)
                    else ToManyUpdateInput
                )
                input_type = type_[  # pyright: ignore[reportInvalidTypeArguments]
                    identifier_input, field.related_dto, upsert_update_fields, upsert_conflict_fields
                ]
        else:
            type_ = RequiredToOneInput if field_required else ToOneInput
            input_type = type_[  # pyright: ignore[reportInvalidTypeArguments]
                identifier_input, field.related_dto, upsert_update_fields, upsert_conflict_fields
            ]
        return input_type if field_required and mode == "create_input" else Optional[input_type]

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[DeclarativeT],
        dto_config: DTOConfig,
        base: type[DTOBase[DeclarativeBase]] | None,
        node: Node[Relation[DeclarativeBase, MappedGraphQLDTOT], None],
        raise_if_no_fields: bool = False,
        *,
        mode: GraphQLPurpose,
        **factory_kwargs: Any,
    ) -> Generator[DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]:
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, mode=mode, **factory_kwargs
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
        parent_field_def: DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]] | None = None,
        current_node: Node[Relation[Any, MappedGraphQLDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        tags: set[str] | None = None,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        mode: GraphQLPurpose,
        **kwargs: Any,
    ) -> type[MappedGraphQLDTOT]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            tags=tags or set() | {mode},
            backend_kwargs=backend_kwargs,
            description=description or self._description(mode),
            mode=mode,
            **kwargs,
        )