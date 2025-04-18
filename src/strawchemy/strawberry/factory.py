from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Self, TypeAlias, TypeVar, get_type_hints, override

from typing_extensions import dataclass_transform

from strawberry import UNSET
from strawberry.types.auto import StrawberryAuto
from strawberry.types.field import StrawberryField
from strawberry.types.object_type import _wrap_dataclass
from strawberry.utils.typing import type_has_annotation
from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.backend.pydantic import PydanticDTOBackend, PydanticDTOT
from strawchemy.dto.base import (
    DTOBackend,
    DTOBase,
    DTOBaseT,
    DTOFactory,
    DTOFieldDefinition,
    MappedDTO,
    ModelFieldT,
    ModelT,
    Relation,
)
from strawchemy.dto.exceptions import EmptyDTOError
from strawchemy.dto.types import DTO_AUTO, DTOConfig, DTOMissingType, Purpose
from strawchemy.dto.utils import config, read_all_partial_config, read_partial, write_all_config
from strawchemy.exceptions import StrawchemyError
from strawchemy.graph import Node
from strawchemy.graphql.dto import (
    AggregateDTO,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    BooleanFilterDTO,
    EnumDTO,
    MappedDataclassGraphQLDTO,
    OrderByDTO,
    StrawchemyDTOAttributes,
    UnmappedDataclassGraphQLDTO,
    UnmappedPydanticGraphQLDTO,
)
from strawchemy.graphql.factories.aggregations import AggregationInspector
from strawchemy.graphql.factories.inputs import (
    AggregateDTOFactory,
    AggregateFilterDTOFactory,
    FilterDTOFactory,
    FilterFunctionInfo,
    OrderByDTOFactory,
)
from strawchemy.graphql.factories.types import RootAggregateTypeDTOFactory, TypeDTOFactory
from strawchemy.graphql.typing import DataclassGraphQLDTO, PydanticGraphQLDTO
from strawchemy.types import DefaultOffsetPagination
from strawchemy.utils import non_optional_type_hint, snake_to_camel

from ._instance import MapperModelInstance
from ._registry import RegistryTypeInfo, StrawberryRegistry
from ._utils import pydantic_from_strawberry_type, strawchemy_type_from_pydantic
from .types import RequiredToManyUpdateInput, RequiredToOneInput, ToManyCreateInput, ToManyUpdateInput, ToOneInput

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Hashable, Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawchemy import Strawchemy
    from strawchemy.dto.types import ExcludeFields, IncludeFields
    from strawchemy.graph import Node
    from strawchemy.graphql.filters import OrderComparison
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol
    from strawchemy.graphql.typing import AggregationType
    from strawchemy.sqlalchemy.hook import QueryHook

    from .typing import GraphQLType, InputType, StrawchemyTypeFromPydantic

__all__ = (
    "StraberryAggregateFactory",
    "StrawberryAggregateFilterInputFactory",
    "StrawberryFilterInputFactory",
    "StrawberryOrderByInputFactory",
    "StrawberryPydanticInputFactory",
    "StrawberryTypeFactory",
)

T = TypeVar("T", bound="DeclarativeBase")
PydanticGraphQLDTOT = TypeVar("PydanticGraphQLDTOT", bound=PydanticGraphQLDTO)
DataclassGraphQLDTOT = TypeVar("DataclassGraphQLDTOT", bound=DataclassGraphQLDTO)
MappedDataclassGraphQLDTOT = TypeVar("MappedDataclassGraphQLDTOT", bound=MappedDataclassGraphQLDTO[Any])
StrawchemyDTOT = TypeVar("StrawchemyDTOT", bound=StrawchemyDTOAttributes)

UpdateType: TypeAlias = Literal["pk", "filter"]


@dataclasses.dataclass(eq=True, frozen=True)
class _ChildOptions:
    pagination: DefaultOffsetPagination | bool = False
    order_by: bool = False


class _StrawberryAggregationInspector(AggregationInspector[ModelT, ModelFieldT]):
    def __init__(
        self,
        inspector: GraphQLInspectorProtocol[Any, ModelFieldT],
        type_registry: StrawberryRegistry | None = None,
    ) -> None:
        super().__init__(inspector)
        self._strawberry_registry = type_registry or StrawberryRegistry()

    @override
    def numeric_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        if dto := super().numeric_field_type(model, dto_config):
            return self._strawberry_registry.register_dataclass(dto, RegistryTypeInfo(dto.__name__, "object"))
        return dto

    @override
    def sum_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        if dto := super().sum_field_type(model, dto_config):
            return self._strawberry_registry.register_dataclass(dto, RegistryTypeInfo(dto.__name__, "object"))
        return dto

    @override
    def min_max_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        if dto := super().min_max_field_type(model, dto_config):
            return self._strawberry_registry.register_dataclass(dto, RegistryTypeInfo(dto.__name__, "object"))
        return dto

    @override
    def arguments_type(
        self, model: type[T], dto_config: DTOConfig, aggregation: AggregationType
    ) -> type[EnumDTO] | None:
        if dto := super().arguments_type(model, dto_config, aggregation):
            return self._strawberry_registry.register_enum(dto)
        return dto


class _StrawberryFactory(DTOFactory[ModelT, ModelFieldT, DTOBaseT]):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DTOBackend[DTOBaseT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper.inspector, backend, handle_cycles, type_map, **kwargs)
        self._mapper = mapper

    def _type_info(
        self,
        dto: type[Any],
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, DTOBaseT], None] | None,
        override: bool = False,
        user_defined: bool = False,
        child_options: _ChildOptions | None = None,
    ) -> RegistryTypeInfo:
        child_options = child_options or _ChildOptions()
        graphql_type = self.graphql_type(dto_config)
        type_info = RegistryTypeInfo(
            name=dto.__name__,
            graphql_type=graphql_type,
            override=override,
            user_defined=user_defined,
            pagination=DefaultOffsetPagination() if child_options.pagination is True else child_options.pagination,
            order_by=child_options.order_by,
        )
        if self._mapper.registry.name_clash(type_info) and current_node is not None:
            type_info = dataclasses.replace(
                type_info, name="".join(node.value.name for node in current_node.path_from_root())
            )
        return type_info

    def _register_pydantic(
        self,
        dto: type[PydanticGraphQLDTOT],
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, DTOBaseT], None] | None,
        all_fields: bool = True,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        base: type[Any] | None = None,
        override: bool = False,
        user_defined: bool = False,
        child_options: _ChildOptions | None = None,
    ) -> type[PydanticGraphQLDTOT]:
        type_info = self._type_info(
            dto,
            dto_config,
            override=override,
            user_defined=user_defined,
            child_options=child_options,
            current_node=current_node,
        )
        self._raise_if_type_conflicts(type_info)
        self._mapper.registry.register_pydantic(
            dto,
            type_info,
            all_fields=all_fields,
            partial=bool(dto_config.partial),
            description=description or dto.__strawchemy_description__,
            directives=directives,
            base=base,
        )
        return dto

    def _register_dataclass(
        self,
        dto: type[StrawchemyDTOT],
        dto_config: DTOConfig,
        current_node: Node[Relation[Any, DTOBaseT], None] | None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
        child_options: _ChildOptions | None = None,
    ) -> type[StrawchemyDTOT]:
        type_info = self._type_info(
            dto,
            dto_config,
            override=override,
            user_defined=user_defined,
            child_options=child_options,
            current_node=current_node,
        )
        self._raise_if_type_conflicts(type_info)
        return self._mapper.registry.register_dataclass(
            dto, type_info, description=description or dto.__strawchemy_description__, directives=directives
        )

    def _check_model_instance_attribute(self, base: type[Any]) -> None:
        instance_attributes = [
            name
            for name, annotation in base.__annotations__.items()
            if type_has_annotation(annotation, MapperModelInstance)
        ]
        if len(instance_attributes) > 1:
            msg = f"{base.__name__} has multiple `MapperModelInstance` attributes: {instance_attributes}"
            raise StrawchemyError(msg)

    def _resolve_config(self, dto_config: DTOConfig, base: type[Any]) -> DTOConfig:
        config = dto_config.with_base_annotations(base)
        try:
            base_annotations = get_type_hints(base, include_extras=True)
        except NameError:
            base_annotations = base.__annotations__
        for name, annotation in base_annotations.items():
            if type_has_annotation(annotation, StrawberryAuto):
                config.annotation_overrides[name] = DTO_AUTO
                base.__annotations__.pop(name)
        return config

    def _raise_if_type_conflicts(self, type_info: RegistryTypeInfo) -> None:
        if self._mapper.registry.non_override_exists(type_info):
            msg = (
                f"""Type `{type_info.name}` cannot be auto generated because it's already declared."""
                """ You may want to set `override=True` on the existing type to use it everywhere."""
            )
            raise StrawchemyError(msg)

    @classmethod
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        raise NotImplementedError

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, DTOBaseT], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        register_type: bool = True,
        user_defined: bool = False,
        **kwargs: Any,
    ) -> type[DTOBaseT]:
        if base:
            self._check_model_instance_attribute(base)
            dto_config = self._resolve_config(dto_config, base)
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs,
            **kwargs,
        )
        if register_type:
            if issubclass(dto, UnmappedPydanticGraphQLDTO):
                return self._register_pydantic(
                    dto,
                    dto_config,
                    current_node=current_node,
                    description=description,
                    directives=directives,
                    override=override,
                    user_defined=user_defined,
                )
            if issubclass(dto, MappedDataclassGraphQLDTO | UnmappedDataclassGraphQLDTO):
                return self._register_dataclass(
                    dto,
                    dto_config,
                    current_node=current_node,
                    description=description,
                    directives=directives,
                    override=override,
                    user_defined=user_defined,
                )
        return dto


class StrawberryDataclassFactory(_StrawberryFactory[ModelT, ModelFieldT, DataclassGraphQLDTOT]):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[DataclassGraphQLDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)

    def _root_input_config(self, model: type[Any], dto_config: DTOConfig, mode: InputType) -> DTOConfig:
        annotations_overrides: dict[str, Any] = {}
        partial = dto_config.partial
        exclude_defaults = dto_config.exclude_defaults
        id_fields = self.inspector.id_field_definitions(model, dto_config)
        # Add PKs for update/delete inputs
        if mode == "update_by_pk":
            if set(dto_config.exclude) & {name for name, _ in id_fields}:
                msg = (
                    "You cannot exclude primary key columns from an input type intended for create or update mutations"
                )
                raise StrawchemyError(msg)
            annotations_overrides |= {name: field.type_hint for name, field in id_fields}
        if mode == "update_by_filter":
            exclude_defaults = True
        if mode in {"update_by_pk", "update_by_filter"}:
            partial = True
        # Exclude default generated PKs for create inputs, if not explicitly included
        elif dto_config.include == "all":
            for name, field in id_fields:
                if self.inspector.has_default(field.model_field):
                    annotations_overrides[name] = field.type_hint | None
        return dataclasses.replace(
            dto_config,
            annotation_overrides=annotations_overrides,
            partial=partial,
            partial_default=UNSET,
            unset_sentinel=UNSET,
            exclude_defaults=exclude_defaults,
        )

    @classmethod
    @override
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        return "input" if dto_config.purpose is Purpose.WRITE else "object"

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: type[T],
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = None,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        child_pagination: bool | DefaultOffsetPagination = False,
        child_order_by: bool = False,
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, ModelFieldT]]] | None = None,
        order_by: type[StrawchemyTypeFromPydantic[OrderByDTO[T, ModelFieldT]]] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHook[T] | Sequence[QueryHook[T]] | None = None,
        override: bool = False,
        purpose: Purpose = Purpose.READ,
    ) -> Callable[[type[Any]], type[DataclassGraphQLDTOT]]:
        def wrapper(class_: type[Any]) -> type[DataclassGraphQLDTOT]:
            dto_config = config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                alias_generator=alias_generator,
                aliases=aliases,
            )
            dto = self.factory(
                model=model,
                dto_config=dto_config,
                base=class_,
                name=name,
                description=description,
                directives=directives,
                query_hook=query_hook,
                override=override,
                user_defined=True,
                child_options=_ChildOptions(pagination=child_pagination, order_by=child_order_by),
            )
            dto.__strawchemy_query_hook__ = query_hook
            if issubclass(dto, MappedDataclassGraphQLDTO):
                dto.__strawchemy_filter__ = filter_input
                dto.__strawchemy_order_by__ = order_by
            return dto

        return wrapper

    def input(
        self,
        model: type[T],
        mode: InputType,
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
        purpose: Purpose = Purpose.WRITE,
    ) -> Callable[[type[Any]], type[DataclassGraphQLDTOT]]:
        def wrapper(class_: type[Any]) -> type[DataclassGraphQLDTOT]:
            dto_config = config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                alias_generator=alias_generator,
                aliases=aliases,
            )
            dto_config = self._root_input_config(model, dto_config, mode)
            return self.factory(
                model=model,
                dto_config=dto_config,
                base=class_,
                name=name,
                description=description,
                directives=directives,
                override=override,
                user_defined=True,
                mode=mode,
            )

        return wrapper


class StrawberryPydanticInputFactory(_StrawberryFactory[ModelT, ModelFieldT, PydanticDTOT]):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: PydanticDTOBackend[PydanticDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._mapper = mapper

    @classmethod
    @override
    def graphql_type(cls, dto_config: DTOConfig) -> GraphQLType:
        return "input"

    def input(
        self,
        model: type[T],
        include: IncludeFields | None = None,
        exclude: ExcludeFields | None = None,
        partial: bool | None = True,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        purpose: Purpose = Purpose.READ,
    ) -> Callable[[type[Any]], type[StrawchemyTypeFromPydantic[PydanticDTOT]]]:
        def wrapper(
            class_: type[Any],
        ) -> type[StrawchemyTypeFromPydantic[PydanticDTOT]]:
            dto_config = config(
                purpose,
                include=include,
                exclude=exclude,
                partial=partial,
                type_map=type_map,
                alias_generator=alias_generator,
                aliases=aliases,
            )
            return strawchemy_type_from_pydantic(
                self.factory(
                    model=model,
                    dto_config=dto_config,
                    base=class_,
                    name=name,
                    description=description,
                    directives=directives,
                    override=override,
                    user_defined=True,
                ),
                strict=True,
            )

        return wrapper


class StraberryAggregateFactory(
    StrawberryDataclassFactory[ModelT, ModelFieldT, AggregateDTO[ModelT]],
    AggregateDTOFactory[ModelT, ModelFieldT, AggregateDTO[ModelT]],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[AggregateDTO[ModelT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or DataclassDTOBackend(AggregateDTO),
            handle_cycles,
            type_map,
            aggregation_builder=_StrawberryAggregationInspector(mapper.inspector),
        )

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, AggregateDTO[ModelT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregations: bool = True,
        **kwargs: Any,
    ) -> type[AggregateDTO[ModelT]]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            aggregations=aggregations,
            backend_kwargs=backend_kwargs,
            **kwargs,
        )


class StrawberryOrderByInputFactory(
    StrawberryPydanticInputFactory[ModelT, ModelFieldT, OrderByDTO[Any, ModelFieldT]],
    OrderByDTOFactory[ModelT, ModelFieldT],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: PydanticDTOBackend[OrderByDTO[ModelT, ModelFieldT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or PydanticDTOBackend(OrderByDTO),
            handle_cycles,
            type_map,
            aggregation_filter_factory=StrawberryAggregateFilterInputFactory(
                mapper, handle_cycles=handle_cycles, type_map=type_map
            ),
        )

    @override
    def _order_by_aggregation_fields(
        self,
        aggregation: FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]],
        model: type[Any],
        dto_config: DTOConfig,
    ) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        dto = super()._order_by_aggregation_fields(aggregation, model, dto_config)
        strawberry_type = self._mapper.registry.register_pydantic(
            dto, RegistryTypeInfo(dto.__name__, "input"), partial=True
        )
        return pydantic_from_strawberry_type(strawberry_type)

    @override
    def _order_by_aggregation(self, model: type[Any], dto_config: DTOConfig) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        dto = super()._order_by_aggregation(model, dto_config)
        strawberry_type = self._mapper.registry.register_pydantic(
            dto, RegistryTypeInfo(dto.__name__, "input"), partial=True
        )
        return pydantic_from_strawberry_type(strawberry_type)

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, OrderByDTO[Any, ModelFieldT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[OrderByDTO[Any, ModelFieldT]]:
        """Generate and register a GraphQL input DTO for ordering query results.

        Creates a Data Transfer Object (DTO) that enables ordering of query results based on model fields
        and aggregations. The generated DTO is registered with the Strawberry registry as an input type.

        Args:
            model: The SQLAlchemy model class for which to generate the ordering DTO.
            dto_config: Configuration for DTO generation, controlling field inclusion and mapping.
                Defaults to read-partial configuration.
            base: Optional base class to inherit from. Used to extend the generated DTO with
                additional fields or methods. Defaults to None.
            name: Optional custom name for the generated DTO. If not provided, a name will be
                generated based on the model name. Defaults to None.
            parent_field_def: Optional reference to the parent DTO field if this DTO is being
                generated as part of a nested structure. Defaults to None.
            current_node: Optional node in the relation graph representing the current position
                in the object hierarchy. Used for handling circular references. Defaults to None.
            raise_if_no_fields: Whether to raise an exception if no orderable fields are found
                in the model. Defaults to False.
            backend_kwargs: Optional dictionary of additional arguments to pass to the DTO backend.
                Defaults to None.
            aggregate_filters: Whether to include fields for ordering by aggregated values
                (e.g., count, sum). Defaults to True.
            description: Optional description of the DTO for GraphQL schema documentation.
                Defaults to None.
            directives: Optional sequence of GraphQL directives to apply to the DTO.
                Defaults to empty tuple.
            **kwargs: Additional keyword arguments passed to the parent factory method.

        Returns:
            A Strawberry-registered Pydantic DTO class that can be used as a GraphQL input type
            for ordering queries. The DTO includes fields for all orderable model attributes and,
            if enabled, aggregation-based ordering.

        Example:
            ```python
            order_by = factory.factory(
                UserModel,
                description="Input type for ordering users",
                aggregate_filters=True
            )
            # Generated DTO will have fields like:
            # - name: OrderDirection  # For ordering by name
            # - age: OrderDirection   # For ordering by age
            # - posts_count: OrderDirection  # If aggregate_filters=True
            ```
        """
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


class StrawberryAggregateFilterInputFactory(
    StrawberryPydanticInputFactory[ModelT, ModelFieldT, AggregateFilterDTO[Any]],
    AggregateFilterDTOFactory[ModelT, ModelFieldT],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: PydanticDTOBackend[AggregateFilterDTO[ModelT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper,
            backend or PydanticDTOBackend(AggregateFilterDTO),
            handle_cycles,
            type_map,
            aggregation_builder=_StrawberryAggregationInspector(mapper.inspector),
        )

    @override
    def _aggregate_function_type(
        self,
        model: type[T],
        dto_config: DTOConfig,
        dto_name: str,
        aggregation: FilterFunctionInfo[T, ModelFieldT, OrderComparison[Any, Any, Any]],
        model_field: DTOMissingType | ModelFieldT,
        parent_field_def: DTOFieldDefinition[ModelT, Any] | None = None,
    ) -> type[AggregationFunctionFilterDTO[ModelT]]:
        self._mapper.registry.register_enum(aggregation.enum_fields)

        dto_type = super()._aggregate_function_type(
            model=model,
            dto_config=dto_config,
            dto_name=dto_name,
            parent_field_def=parent_field_def,
            aggregation=aggregation,
            model_field=model_field,
        )
        partial_fields = {"distinct"}
        if aggregation.function == "count":
            partial_fields.add("arguments")
        strawberry_type = self._mapper.registry.register_pydantic(
            dto_type,
            RegistryTypeInfo(dto_type.__name__, "input"),
            partial_fields=partial_fields,
            description=f"Boolean expression to compare {aggregation.function} aggregation.",
        )
        return pydantic_from_strawberry_type(strawberry_type)


class StrawberryTypeFactory(
    StrawberryDataclassFactory[ModelT, ModelFieldT, MappedDataclassGraphQLDTO[Any]],
    TypeDTOFactory[ModelT, ModelFieldT, MappedDataclassGraphQLDTO[Any]],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[MappedDataclassGraphQLDTO[Any]],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        order_by_factory: StrawberryOrderByInputFactory[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            mapper,
            backend,
            handle_cycles,
            type_map,
            aggregation_factory=StraberryAggregateFactory(mapper, handle_cycles=handle_cycles, type_map=type_map),
            **kwargs,
        )
        self._order_by_factory = order_by_factory or StrawberryOrderByInputFactory(
            mapper, handle_cycles=handle_cycles, type_map=type_map
        )

    def _dataclass_merge(
        self,
        dto: type[MappedDataclassGraphQLDTO[Any]],
        base: type[Any] | None,
        pagination: bool | DefaultOffsetPagination = False,
        order_by: bool = False,
    ) -> type[Any]:
        base_dataclass_fields: dict[str, tuple[Any, dataclasses.Field[Any]]] = {}
        dto_dataclass_fields = {field.name: field for field in dataclasses.fields(dto)}
        attributes: dict[str, Any] = {}

        for field in dto.__strawchemy_field_map__.values():
            if field.is_relation and field.uselist:
                related = Self if field.related_dto is dto else field.related_dto
                type_annotation = list[related] if related is not None else field.type_
                assert field.related_model
                order_by_input = None
                if order_by:
                    order_by_input = strawchemy_type_from_pydantic(
                        self._order_by_factory.factory(field.related_model, read_all_partial_config),
                        strict=True,
                    )
                dc_field = self._mapper.field(
                    pagination=pagination, order_by=order_by_input, root_field=False, graphql_type=type_annotation
                )
                attributes[field.name] = dc_field
            else:
                dc_field = dto_dataclass_fields[field.name]
                type_annotation = dc_field.type
                base_dataclass_fields[field.name] = (type_annotation, dc_field)

        bases = (dto,)

        if base:
            bases = (dto, base)
            for field in dataclasses.fields(_wrap_dataclass(base)):
                base_dataclass_fields[field.name] = (field.type, field)
                if isinstance(field, StrawberryField) and field.base_resolver and field.python_name:
                    attributes[field.python_name] = field

        strawberry_base = dataclasses.make_dataclass(
            dto.__name__,
            tuple((name, *value) for name, value in base_dataclass_fields.items()),
            bases=bases,
            kw_only=True,
            module=dto.__module__,
        )
        for name, value in attributes.items():
            setattr(strawberry_base, name, value)
        return strawberry_base

    @override
    def _cache_key(
        self,
        model: type[Any],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None],
        *,
        child_options: _ChildOptions | None = None,
        **factory_kwargs: Any,
    ) -> Hashable:
        return (super()._cache_key(model, dto_config, node, **factory_kwargs), child_options)

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        child_options: _ChildOptions | None = None,
        aggregations: bool = True,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        override: bool = False,
        user_defined: bool = False,
        **kwargs: Any,
    ) -> type[MappedDataclassGraphQLDTO[Any]]:
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            aggregations=aggregations,
            backend_kwargs=backend_kwargs,
            register_type=False,
            override=override,
            child_options=child_options,
            **kwargs,
        )
        child_options = child_options or _ChildOptions()
        if self.graphql_type(dto_config) == "object":
            dto = self._dataclass_merge(dto, base, pagination=child_options.pagination, order_by=child_options.order_by)
        return self._register_dataclass(
            dto,
            dto_config=dto_config,
            description=description,
            directives=directives,
            override=override,
            user_defined=user_defined,
            child_options=child_options,
            current_node=current_node,
        )


class StrawberryInputFactory(StrawberryTypeFactory[ModelT, ModelFieldT]):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[MappedDataclassGraphQLDTO[Any]],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._identifier_input_dto_builder = DataclassDTOBackend(MappedDataclassGraphQLDTO[ModelT])
        self._identifier_input_dto_factory = DTOFactory(self.inspector, self.backend)

    def _identifier_input(
        self,
        field: DTOFieldDefinition[ModelT, ModelFieldT],
        node: Node[Relation[ModelT, MappedDataclassGraphQLDTO[Any]], None],
    ) -> type[MappedDTO[Any]]:
        name = f"{node.root.value.model.__name__}{snake_to_camel(field.name)}IdFieldsInput"
        related_model = field.related_model
        assert related_model
        id_fields = list(self.inspector.id_field_definitions(related_model, write_all_config))
        dto_config = DTOConfig(Purpose.WRITE, include={name for name, _ in id_fields})
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

        return self._register_dataclass(base, dto_config, node, description="Identifier input")

    @override
    def _cache_key(
        self,
        model: type[Any],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None],
        *,
        child_options: _ChildOptions | None = None,
        mode: InputType,
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
        node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None] | None = None,
    ) -> str:
        return f"{node.root.value.model.__name__ if node else ''}{base_name}Input"

    @override
    def should_exclude_field(
        self,
        field: DTOFieldDefinition[Any, ModelFieldT],
        dto_config: DTOConfig,
        node: Node[Relation[Any, MappedDataclassGraphQLDTO[ModelT]], None],
        has_override: bool,
    ) -> bool:
        return super().should_exclude_field(field, dto_config, node, has_override) or self.inspector.is_foreign_key(
            field.model_field
        )

    @override
    def _resolve_type(
        self,
        field: DTOFieldDefinition[ModelT, ModelFieldT],
        dto_config: DTOConfig,
        node: Node[Relation[ModelT, MappedDataclassGraphQLDTO[Any]], None],
        *,
        mode: InputType,
        **factory_kwargs: Any,
    ) -> Any:
        if not field.is_relation:
            return super()._resolve_basic_type(field, dto_config)
        self._resolve_relation_type(field, dto_config, node, mode=mode, **factory_kwargs)
        identifier_input = self._identifier_input(field, node)
        field_required = self.inspector.required(field.model_field)
        if field.uselist:
            if mode == "create":
                input_type = ToManyCreateInput[identifier_input, field.related_dto]  # pyright: ignore[reportInvalidTypeArguments]
            else:
                type_ = (
                    RequiredToManyUpdateInput
                    if self.inspector.reverse_relation_required(field.model_field)
                    else ToManyUpdateInput
                )
                input_type = type_[identifier_input, field.related_dto]  # pyright: ignore[reportInvalidTypeArguments]
        else:
            type_ = RequiredToOneInput if field_required else ToOneInput
            input_type = type_[identifier_input, field.related_dto]  # pyright: ignore[reportInvalidTypeArguments]
        return input_type if field_required else input_type | None

    @override
    def iter_field_definitions(
        self,
        name: str,
        model: type[T],
        dto_config: DTOConfig,
        base: type[DTOBase[ModelT]] | None,
        node: Node[Relation[ModelT, MappedDataclassGraphQLDTO[ModelT]], None],
        raise_if_no_fields: bool = False,
        *,
        mode: InputType,
        **factory_kwargs: Any,
    ) -> Generator[DTOFieldDefinition[ModelT, ModelFieldT], None, None]:
        for field in super().iter_field_definitions(
            name, model, dto_config, base, node, raise_if_no_fields, mode=mode, **factory_kwargs
        ):
            if mode == "update_by_pk" and self.inspector.is_primary_key(field.model_field):
                field.type_ = non_optional_type_hint(field.type_)
            yield field

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        mode: InputType,
        **kwargs: Any,
    ) -> type[MappedDataclassGraphQLDTO[Any]]:
        return super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            backend_kwargs=backend_kwargs,
            description=description or f"GraphQL {mode} input type",
            mode=mode,
            **kwargs,
        )


class StrawberryFilterInputFactory(
    StrawberryPydanticInputFactory[ModelT, ModelFieldT, BooleanFilterDTO[Any, ModelFieldT]],
    FilterDTOFactory[ModelT, ModelFieldT, BooleanFilterDTO[Any, ModelFieldT]],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: PydanticDTOBackend[BooleanFilterDTO[Any, ModelFieldT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        aggregate_filter_factory: StrawberryAggregateFilterInputFactory[ModelT, ModelFieldT] | None = None,
    ) -> None:
        super().__init__(
            mapper=mapper,
            backend=backend or PydanticDTOBackend(BooleanFilterDTO),
            handle_cycles=handle_cycles,
            type_map=type_map,
            aggregation_filter_factory=aggregate_filter_factory
            or StrawberryAggregateFilterInputFactory(mapper, handle_cycles=handle_cycles, type_map=type_map),
        )

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, BooleanFilterDTO[Any, ModelFieldT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregate_filters: bool = True,
        **kwargs: Any,
    ) -> type[BooleanFilterDTO[Any, ModelFieldT]]:
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


class StrawberryRootAggregateTypeFactory(
    StrawberryTypeFactory[ModelT, ModelFieldT],
    RootAggregateTypeDTOFactory[ModelT, ModelFieldT, MappedDataclassGraphQLDTO[Any]],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[MappedDataclassGraphQLDTO[Any]],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        type_factory: StrawberryTypeFactory[ModelT, ModelFieldT] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            mapper,
            backend,
            handle_cycles,
            type_map,
            type_factory=type_factory
            or StrawberryTypeFactory(mapper, backend, handle_cycles=handle_cycles, type_map=type_map),
            **kwargs,
        )
