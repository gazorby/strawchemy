from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union

from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawberry.annotation import StrawberryAnnotation
from strawberry.types.arguments import StrawberryArgument
from typing_extensions import Self, override

from sqlalchemy import JSON
from strawchemy.constants import AGGREGATIONS_KEY, JSON_PATH_KEY, NODES_KEY
from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.base import DTOFactory, MappedDTO
from strawchemy.dto.exceptions import EmptyDTOError
from strawchemy.dto.types import DTOConfig, DTOMissing, Purpose
from strawchemy.dto.utils import read_all_partial_config, read_partial, write_all_config
from strawchemy.graph import Node
from strawchemy.strawberry.dto import (
    AggregateDTO,
    AggregateFieldDefinition,
    DTOKey,
    EnumDTO,
    FunctionFieldDefinition,
    GraphQLFieldDefinition,
    MappedStrawberryGraphQLDTO,
)
from strawchemy.strawberry.mutation.types import (
    RequiredToManyUpdateInput,
    RequiredToOneInput,
    ToManyCreateInput,
    ToManyUpdateInput,
    ToOneInput,
)
from strawchemy.strawberry.typing import AggregateDTOT, GraphQLDTOT, GraphQLPurpose
from strawchemy.utils import get_annotations, non_optional_type_hint, snake_to_camel

from .aggregations import AggregationInspector
from .base import GraphQLDTOFactory, MappedGraphQLDTOT, StrawchemyMappedFactory, _ChildOptions
from .enum import EnumDTOFactory, UpsertConflictFieldsEnumDTOBackend
from .inputs import OrderByDTOFactory

if TYPE_CHECKING:
    from collections.abc import Generator, Hashable, Sequence
    from enum import Enum

    from strawchemy import Strawchemy
    from strawchemy.dto.base import DTOBackend, DTOBase, DTOFieldDefinition, Relation
    from strawchemy.graph import Node
    from strawchemy.sqlalchemy.inspector import SQLAlchemyGraphQLInspector
    from strawchemy.sqlalchemy.typing import DeclarativeT
    from strawchemy.types import DefaultOffsetPagination


__all__ = ("AggregateDTOFactory", "DistinctOnFieldsDTOFactory", "RootAggregateTypeDTOFactory", "TypeDTOFactory")

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

    def _update_fields(
        self,
        dto: type[GraphQLDTOT],
        base: type[Any] | None,
        pagination: bool | DefaultOffsetPagination = False,
        order_by: bool = False,
    ) -> type[GraphQLDTOT]:
        attributes: dict[str, Any] = {}
        annotations: dict[str, Any] = {}

        for field in dto.__strawchemy_field_map__.values():
            if field.is_relation and field.uselist:
                related = Self if field.related_dto is dto else field.related_dto
                type_annotation = list[related] if related is not None else field.type_
                assert field.related_model
                order_by_input = None
                if order_by:
                    order_by_input = self._order_by_factory.factory(field.related_model, read_all_partial_config)
                strawberry_field = self._mapper.field(pagination=pagination, order_by=order_by_input, root_field=False)
                attributes[field.name] = strawberry_field
                annotations[field.name] = type_annotation
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
    def _cache_key(
        self,
        model: type[Any],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedGraphQLDTOT], None],
        *,
        child_options: _ChildOptions,
        **factory_kwargs: Any,
    ) -> Hashable:
        return (super()._cache_key(model, dto_config, node, **factory_kwargs), child_options)

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
        child_options: _ChildOptions | None = None,
        aggregations: bool = True,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
        register_type: bool = True,
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
            aggregations=aggregations if dto_config.purpose is Purpose.READ else False,
            register_type=False,
            override=override,
            child_options=child_options,
            **kwargs,
        )
        child_options = child_options or _ChildOptions()
        if self.graphql_type(dto_config) == "object":
            dto = self._update_fields(dto, base, pagination=child_options.pagination, order_by=child_options.order_by)
        if register_type:
            return self._register_type(
                dto,
                dto_config=dto_config,
                description=description,
                directives=directives,
                override=override,
                user_defined=user_defined,
                child_options=child_options,
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
        child_options: _ChildOptions,
        mode: GraphQLPurpose,
        **factory_kwargs: Any,
    ) -> Hashable:
        return (
            super()._cache_key(model, dto_config, node, child_options=child_options, **factory_kwargs),
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
