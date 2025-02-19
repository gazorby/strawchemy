from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self, TypeVar, override

from typing_extensions import dataclass_transform

from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
from strawberry.experimental.pydantic.utils import get_strawberry_type_from_model
from strawberry.types.field import StrawberryField
from strawberry.types.object_type import _wrap_dataclass
from strawberry.utils.typing import type_has_annotation
from strawchemy.dto.backend.dataclass import DataclassDTOBackend, DataclassDTOT
from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTOBackend, PydanticDTOT
from strawchemy.dto.base import DTOBackend, DTOBaseT, DTOFactory, DTOFieldDefinition, ModelFieldT, ModelT, Relation
from strawchemy.dto.types import DTOConfig, DTOMissingType, Purpose
from strawchemy.dto.utils import config
from strawchemy.graph import Node
from strawchemy.graphql.dto import (
    AggregateDTO,
    AggregateFilterDTO,
    AggregationFunctionFilterDTO,
    BooleanFilterDTO,
    EnumDTO,
    MappedDataclassGraphQLDTO,
    OrderByDTO,
    UnmappedDataclassGraphQLDTO,
)
from strawchemy.graphql.factory import (
    AggregateDTOFactory,
    AggregateFilterDTOFactory,
    AggregationInspector,
    FilterDTOFactory,
    FilterFunctionInfo,
    OrderByDTOFactory,
    RootAggregateTypeDTOFactory,
    TypeDTOFactory,
    dto_config_read_partial,
)
from strawchemy.graphql.typing import DataclassGraphQLDTO, PydanticGraphQLDTO

from ._instance import MapperModelInstance
from ._registry import StrawberryRegistry
from ._utils import pydantic_from_strawberry_type, strawberry_type_from_pydantic
from .exceptions import StrawchemyError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawberry.experimental.pydantic.conversion_types import StrawberryTypeFromPydantic
    from strawchemy import Strawchemy
    from strawchemy.graph import Node
    from strawchemy.graphql.filters import NumericComparison
    from strawchemy.graphql.inspector import GraphQLInspectorProtocol
    from strawchemy.graphql.typing import AggregationType
    from strawchemy.sqlalchemy.typing import QueryHookCallable

__all__ = (
    "StraberryAggregateFactory",
    "StrawberryAggregateFilterFactory",
    "StrawberryFilterFactory",
    "StrawberryOrderByFactory",
    "StrawberryPydanticFactory",
    "StrawberryTypeFactory",
)

T = TypeVar("T", bound="DeclarativeBase")
PydanticGraphQLDTOT = TypeVar("PydanticGraphQLDTOT", bound=PydanticGraphQLDTO)
DataclassGraphQLDTOT = TypeVar("DataclassGraphQLDTOT", bound=DataclassGraphQLDTO)


class _StrawberryAggregationInspector(AggregationInspector[ModelT, ModelFieldT]):
    def __init__(
        self, inspector: GraphQLInspectorProtocol[Any, ModelFieldT], type_registry: StrawberryRegistry | None = None
    ) -> None:
        super().__init__(inspector)
        self._strawberry_registry = type_registry or StrawberryRegistry()

    @override
    def numeric_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        dto = super().numeric_field_type(model, dto_config)
        if dto:
            return self._strawberry_registry.register_dataclass(dto, dto.__name__)
        return dto

    @override
    def sum_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        dto = super().sum_field_type(model, dto_config)
        if dto:
            return self._strawberry_registry.register_dataclass(dto, dto.__name__)
        return dto

    @override
    def min_max_field_type(self, model: type[T], dto_config: DTOConfig) -> type[UnmappedDataclassGraphQLDTO[T]] | None:
        dto = super().min_max_field_type(model, dto_config)
        if dto:
            return self._strawberry_registry.register_dataclass(dto, dto.__name__)
        return dto

    @override
    def arguments_type(
        self, model: type[T], dto_config: DTOConfig, aggregation: AggregationType
    ) -> type[EnumDTO] | None:
        dto = super().arguments_type(model, dto_config, aggregation)
        if dto:
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

    @classmethod
    def _config(
        cls,
        purpose: Purpose,
        exclude: set[str] | None = None,
        partial: bool = False,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
    ) -> DTOConfig:
        config = DTOConfig(purpose, partial=partial, alias_generator=alias_generator)
        if exclude:
            config.exclude = exclude
        if type_map:
            config.type_map = type_map
        if aliases:
            config.aliases = aliases
        return config

    def _register_pydantic(
        self,
        dto: type[PydanticGraphQLDTOT],
        dto_config: DTOConfig,
        all_fields: bool = True,
        is_input: bool = False,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        base: type[Any] | None = None,
    ) -> type[PydanticGraphQLDTOT]:
        self._mapper.registry.register_pydantic(
            dto,
            all_fields=all_fields,
            is_input=is_input,
            partial=bool(dto_config.partial),
            description=description or dto.__strawchemy_description__,
            directives=directives,
            name=dto.__name__,
            base=base,
        )
        return dto

    def _register_dataclass(
        self,
        dto: type[DataclassGraphQLDTOT],
        is_input: bool = False,
        description: str | None = None,
        directives: Sequence[object] | None = (),
    ) -> type[DataclassGraphQLDTOT]:
        return self._mapper.registry.register_dataclass(
            dto,
            is_input=is_input,
            description=description or dto.__strawchemy_description__,
            directives=directives,
            name=dto.__name__,
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


class StrawberryDataclassFactory(_StrawberryFactory[ModelT, ModelFieldT, DataclassDTOT]):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: DataclassDTOBackend[DataclassDTOT],
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(mapper, backend, handle_cycles, type_map, **kwargs)
        self._mapper = mapper

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: type[T],
        exclude: set[str] | None = None,
        partial: bool = False,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[DataclassDTOT]]:
        def wrapper(class_: type[Any]) -> type[DataclassDTOT]:
            return self.factory(
                model=model,
                dto_config=self._config(
                    Purpose.READ,
                    exclude=exclude,
                    partial=partial,
                    type_map=type_map,
                    alias_generator=alias_generator,
                    aliases=aliases,
                ),
                base=class_,
                name=name,
                description=description,
                directives=directives,
                **kwargs,
            )

        return wrapper


class StrawberryPydanticFactory(_StrawberryFactory[ModelT, ModelFieldT, PydanticDTOT]):
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

    @dataclass_transform(order_default=True, kw_only_default=True)
    def input(
        self,
        model: type[T],
        dto_config: DTOConfig | Purpose = dto_config_read_partial,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[StrawberryTypeFromPydantic[PydanticDTOT]]]:
        def wrapper(class_: type[Any]) -> type[StrawberryTypeFromPydantic[PydanticDTOT]]:
            return strawberry_type_from_pydantic(
                self.factory(
                    model=model,
                    dto_config=config(dto_config) if isinstance(dto_config, Purpose) else dto_config,
                    base=class_,
                    name=name,
                    description=description,
                    directives=directives,
                    **kwargs,
                ),
                strict=True,
            )

        return wrapper

    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: type[T],
        exclude: set[str] | None = None,
        partial: bool = False,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[StrawberryTypeFromPydantic[MappedPydanticDTO[T]]]]:
        def wrapper(class_: type[Any]) -> type[StrawberryTypeFromPydantic[MappedPydanticDTO[T]]]:
            return get_strawberry_type_from_model(
                self.factory(
                    model=model,
                    dto_config=self._config(
                        Purpose.READ,
                        exclude=exclude,
                        partial=partial,
                        type_map=type_map,
                        alias_generator=alias_generator,
                        aliases=aliases,
                    ),
                    base=class_,
                    name=name,
                    description=description,
                    directives=directives,
                    **kwargs,
                )
            )

        return wrapper

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, PydanticDTOT], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> type[PydanticDTOT]:
        if base:
            self._check_model_instance_attribute(base)
        return super().factory(
            model, dto_config, base, name, parent_field_def, current_node, raise_if_no_fields, backend_kwargs, **kwargs
        )


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
        dto_config: DTOConfig = dto_config_read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, AggregateDTO[ModelT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> type[AggregateDTO[ModelT]]:
        return self._register_dataclass(
            super().factory(
                model,
                dto_config,
                base,
                name,
                parent_field_def,
                current_node,
                raise_if_no_fields,
                backend_kwargs,
                **kwargs,
            ),
            is_input=False,
            description=description,
            directives=directives,
        )


class StrawberryOrderByFactory(
    StrawberryPydanticFactory[ModelT, ModelFieldT, OrderByDTO[Any, ModelFieldT]],
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
            aggregation_filter_factory=StrawberryAggregateFilterFactory(
                mapper, handle_cycles=handle_cycles, type_map=type_map
            ),
        )

    @override
    def _order_by_aggregation_fields(
        self,
        aggregation: FilterFunctionInfo[ModelT, ModelFieldT, NumericComparison[Any, Any, Any]],
        model: type[Any],
        dto_config: DTOConfig,
    ) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        dto = super()._order_by_aggregation_fields(aggregation, model, dto_config)
        strawberry_type = self._mapper.registry.register_pydantic(dto, dto.__name__, is_input=True, partial=True)
        return pydantic_from_strawberry_type(strawberry_type)

    @override
    def _order_by_aggregation(self, model: type[Any], dto_config: DTOConfig) -> type[OrderByDTO[ModelT, ModelFieldT]]:
        dto = super()._order_by_aggregation(model, dto_config)
        strawberry_type = self._mapper.registry.register_pydantic(dto, dto.__name__, is_input=True, partial=True)
        return pydantic_from_strawberry_type(strawberry_type)

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = dto_config_read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, OrderByDTO[Any, ModelFieldT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        aggregate_filters: bool = True,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
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
        return self._register_pydantic(
            super().factory(
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
            ),
            dto_config,
            is_input=True,
            description=description,
            directives=directives,
        )


class StrawberryAggregateFilterFactory(
    StrawberryPydanticFactory[ModelT, ModelFieldT, AggregateFilterDTO[ModelT]],
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
        aggregation: FilterFunctionInfo[T, ModelFieldT, NumericComparison[Any, Any, Any]],
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
            pydantic_type=dto_type,
            name=dto_type.__name__,
            is_input=True,
            partial_fields=partial_fields,
            description=f"Boolean expression to compare {aggregation.function} aggregation.",
        )
        return pydantic_from_strawberry_type(strawberry_type)

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = dto_config_read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, AggregateFilterDTO[ModelT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> type[AggregateFilterDTO[ModelT]]:
        return self._register_pydantic(
            super().factory(
                model,
                dto_config,
                base,
                name,
                parent_field_def,
                current_node,
                raise_if_no_fields,
                backend_kwargs,
                **kwargs,
            ),
            dto_config,
            is_input=True,
            description=description,
            directives=directives,
        )


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
        self._order_by_factory = StrawberryOrderByFactory(mapper, handle_cycles=handle_cycles, type_map=type_map)

    def _dataclass_merge(self, dto: type[MappedDataclassGraphQLDTO[Any]], base: type[Any] | None) -> type[Any]:
        base_dataclass_fields: dict[str, tuple[Any, dataclasses.Field[Any]]] = {}
        dto_dataclass_fields = {field.name: field for field in dataclasses.fields(dto)}
        attributes: dict[str, Any] = {}

        for field in dto.__strawchemy_field_map__.values():
            if field.is_relation and field.uselist:
                type_annotation = list[Self if field.related_dto is dto else field.related_dto]
                assert field.related_model
                order_by = strawberry_type_from_pydantic(
                    self._order_by_factory.factory(field.related_model), strict=True
                )
                dc_field = self._mapper.field(order_by=order_by, root_field=False, graphql_type=type_annotation)
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
            slots=True,
        )
        for name, value in attributes.items():
            setattr(strawberry_base, name, value)
        return strawberry_base

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = dto_config_read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, MappedDataclassGraphQLDTO[Any]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        *,
        aggregations: bool = True,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> type[MappedDataclassGraphQLDTO[T]]:
        dto = super().factory(
            model,
            dto_config,
            base,
            name,
            parent_field_def,
            current_node,
            raise_if_no_fields,
            aggregations=aggregations,
            backend_kwargs=(backend_kwargs or {}) | {"slots": True},
            **kwargs,
        )
        return self._register_dataclass(
            self._dataclass_merge(dto, base), is_input=False, description=description, directives=directives
        )

    @override
    @dataclass_transform(order_default=True, kw_only_default=True)
    def type(
        self,
        model: type[T],
        exclude: set[str] | None = None,
        partial: bool = False,
        type_map: Mapping[Any, Any] | None = None,
        aliases: Mapping[str, str] | None = None,
        alias_generator: Callable[[str], str] | None = None,
        name: str | None = None,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        query_hook: QueryHookCallable[T] | Sequence[QueryHookCallable[T]] | None = None,
        **kwargs: Any,
    ) -> Callable[[type[Any]], type[MappedDataclassGraphQLDTO[T]]]:
        def wrapper(class_: type[Any]) -> type[MappedDataclassGraphQLDTO[T]]:
            dto = self.factory(
                model=model,
                dto_config=self._config(
                    Purpose.READ,
                    exclude=exclude,
                    partial=partial,
                    type_map=type_map,
                    alias_generator=alias_generator,
                    aliases=aliases,
                ),
                base=class_,
                name=name,
                description=description,
                directives=directives,
                **kwargs,
            )
            dto.__strawchemy_query_hook__ = query_hook
            return dto

        return wrapper


class StrawberryFilterFactory(
    StrawberryPydanticFactory[ModelT, ModelFieldT, BooleanFilterDTO[Any, ModelFieldT]],
    FilterDTOFactory[ModelT, ModelFieldT, BooleanFilterDTO[Any, ModelFieldT]],
):
    def __init__(
        self,
        mapper: Strawchemy[ModelT, ModelFieldT],
        backend: PydanticDTOBackend[BooleanFilterDTO[Any, ModelFieldT]] | None = None,
        handle_cycles: bool = True,
        type_map: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(
            mapper=mapper,
            backend=backend or PydanticDTOBackend(BooleanFilterDTO),
            handle_cycles=handle_cycles,
            type_map=type_map,
            aggregation_filter_factory=StrawberryAggregateFilterFactory(
                mapper, handle_cycles=handle_cycles, type_map=type_map
            ),
        )

    @override
    def factory(
        self,
        model: type[T],
        dto_config: DTOConfig = dto_config_read_partial,
        base: type[Any] | None = None,
        name: str | None = None,
        parent_field_def: DTOFieldDefinition[ModelT, ModelFieldT] | None = None,
        current_node: Node[Relation[Any, BooleanFilterDTO[Any, ModelFieldT]], None] | None = None,
        raise_if_no_fields: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
        aggregate_filters: bool = True,
        *,
        description: str | None = None,
        directives: Sequence[object] | None = (),
        **kwargs: Any,
    ) -> type[BooleanFilterDTO[Any, ModelFieldT]]:
        return self._register_pydantic(
            super().factory(
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
            ),
            dto_config,
            is_input=True,
            description=description,
            directives=directives,
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
        **kwargs: Any,
    ) -> None:
        super().__init__(
            mapper,
            backend,
            handle_cycles,
            type_map,
            type_factory=StrawberryTypeFactory(mapper, backend, handle_cycles=handle_cycles, type_map=type_map),
            **kwargs,
        )
