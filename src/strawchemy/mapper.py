from __future__ import annotations

import dataclasses
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, TypeVar, overload

from strawberry.annotation import StrawberryAnnotation

from .config.base import StrawchemyConfig
from .dto.backend.strawberry import StrawberrryDTOBackend
from .dto.base import TYPING_NS
from .strawberry._field import (
    StrawchemyCreateMutationField,
    StrawchemyDeleteMutationField,
    StrawchemyField,
    StrawchemyUpdateMutationField,
)
from .strawberry._registry import StrawberryRegistry
from .strawberry.dto import BooleanFilterDTO, EnumDTO, MappedStrawberryGraphQLDTO, OrderByDTO, OrderByEnum
from .strawberry.factories.inputs import AggregateFilterDTOFactory, BooleanFilterDTOFactory
from .strawberry.factories.types import (
    DistinctOnFieldsDTOFactory,
    InputFactory,
    OrderByDTOFactory,
    RootAggregateTypeDTOFactory,
    TypeDTOFactory,
)
from .strawberry.mutation import types
from .types import DefaultOffsetPagination

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawberry import BasePermission
    from strawberry.extensions.field_extension import FieldExtension
    from strawberry.types.arguments import StrawberryArgument
    from strawberry.types.field import _RESOLVER_TYPE
    from strawchemy.validation.pydantic import PydanticMapper

    from .sqlalchemy.hook import QueryHook
    from .sqlalchemy.typing import QueryHookCallable
    from .strawberry.typing import FilterStatementCallable, MappedGraphQLDTO
    from .typing import AnyRepository, SupportedDialect
    from .validation.base import ValidationProtocol


T = TypeVar("T", bound="DeclarativeBase")

_TYPES_NS = TYPING_NS | vars(types)

__all__ = ("Strawchemy",)


class Strawchemy:
    def __init__(self, config: StrawchemyConfig | SupportedDialect) -> None:
        dto_backend = StrawberrryDTOBackend(MappedStrawberryGraphQLDTO)

        self.config = StrawchemyConfig(config) if isinstance(config, str) else config
        self.registry = StrawberryRegistry()

        self._aggregate_filter_factory = AggregateFilterDTOFactory(self)
        self._filter_factory = BooleanFilterDTOFactory(self, aggregate_filter_factory=self._aggregate_filter_factory)
        self._order_by_factory = OrderByDTOFactory(self)
        self._distinct_on_enum_factory = DistinctOnFieldsDTOFactory(self.config.inspector)
        self._type_factory = TypeDTOFactory(self, dto_backend, order_by_factory=self._order_by_factory)
        self._input_factory = InputFactory(self, dto_backend)
        self._aggregation_factory = RootAggregateTypeDTOFactory(self, dto_backend, type_factory=self._type_factory)

        self.filter = self._filter_factory.input
        self.aggregate_filter = self._aggregate_filter_factory.input
        self.distinct_on = self._distinct_on_enum_factory.decorator
        self.input = self._input_factory.input
        self.create_input = partial(self._input_factory.input, mode="create")
        self.pk_update_input = partial(self._input_factory.input, mode="update_by_pk")
        self.filter_update_input = partial(self._input_factory.input, mode="update_by_filter")
        self.order = self._order_by_factory.input
        self.type = self._type_factory.type
        self.aggregate = self._aggregation_factory.type

        # Register common types
        self.registry.register_enum(OrderByEnum, "OrderByEnum")

    def _annotation_namespace(self) -> dict[str, Any]:
        return self.registry.namespace("object") | _TYPES_NS

    @cached_property
    def pydantic(self) -> PydanticMapper:
        from .validation.pydantic import PydanticMapper

        return PydanticMapper(self)

    @overload
    def field(
        self,
        resolver: _RESOLVER_TYPE[Any],
        *,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        arguments: list[StrawberryArgument] | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHook[Any] | Sequence[QueryHook[Any]] | None = None,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        root_field: bool = True,
    ) -> StrawchemyField: ...

    @overload
    def field(
        self,
        *,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        arguments: list[StrawberryArgument] | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHookCallable[Any] | Sequence[QueryHookCallable[Any]] | None = None,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        root_field: bool = True,
    ) -> Any: ...

    def field(
        self,
        resolver: _RESOLVER_TYPE[Any] | None = None,
        *,
        filter_input: type[BooleanFilterDTO] | None = None,
        order_by: type[OrderByDTO] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        arguments: list[StrawberryArgument] | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHookCallable[Any] | Sequence[QueryHookCallable[Any]] | None = None,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        root_field: bool = True,
    ) -> Any:
        namespace = self._annotation_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type
        execution_options_ = execution_options if execution_options is not None else self.config.execution_options
        pagination = (
            DefaultOffsetPagination(limit=self.config.pagination_default_limit) if pagination is True else pagination
        )
        if pagination is None:
            pagination = self.config.pagination
        id_field_name = id_field_name or self.config.default_id_field_name

        field = StrawchemyField(
            config=self.config,
            repository_type=repository_type_,
            root_field=root_field,
            filter_statement=filter_statement,
            execution_options=execution_options_,
            filter_type=filter_input,
            order_by=order_by,
            pagination=pagination,
            id_field_name=id_field_name,
            distinct_on=distinct_on,
            root_aggregations=root_aggregations,
            query_hook=query_hook,
            python_name=None,
            graphql_name=name,
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=permission_classes or [],
            deprecation_reason=deprecation_reason,
            default=default,
            default_factory=default_factory,
            metadata=metadata,
            directives=directives,
            extensions=extensions or [],
            registry_namespace=namespace,
            description=description,
            arguments=arguments,
        )
        return field(resolver) if resolver else field

    def create(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        resolver: _RESOLVER_TYPE[Any] | None = None,
        *,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        validation: ValidationProtocol[T] | None = None,
    ) -> Any:
        namespace = self._annotation_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type

        field = StrawchemyCreateMutationField(
            input_type,
            config=self.config,
            repository_type=repository_type_,
            python_name=None,
            graphql_name=name,
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=permission_classes or [],
            deprecation_reason=deprecation_reason,
            default=default,
            default_factory=default_factory,
            metadata=metadata,
            directives=directives,
            extensions=extensions or [],
            registry_namespace=namespace,
            description=description,
            validation=validation,
        )
        return field(resolver) if resolver else field

    def update(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        filter_input: type[BooleanFilterDTO],
        resolver: _RESOLVER_TYPE[Any] | None = None,
        *,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        validation: ValidationProtocol[T] | None = None,
    ) -> Any:
        namespace = self._annotation_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type

        field = StrawchemyUpdateMutationField(
            config=self.config,
            input_type=input_type,
            filter_type=filter_input,
            repository_type=repository_type_,
            python_name=None,
            graphql_name=name,
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=permission_classes or [],
            deprecation_reason=deprecation_reason,
            default=default,
            default_factory=default_factory,
            metadata=metadata,
            directives=directives,
            extensions=extensions or [],
            registry_namespace=namespace,
            description=description,
            validation=validation,
        )
        return field(resolver) if resolver else field

    def update_by_ids(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        resolver: _RESOLVER_TYPE[Any] | None = None,
        *,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
        validation: ValidationProtocol[T] | None = None,
    ) -> Any:
        namespace = self._annotation_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type

        field = StrawchemyUpdateMutationField(
            config=self.config,
            input_type=input_type,
            repository_type=repository_type_,
            python_name=None,
            graphql_name=name,
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=permission_classes or [],
            deprecation_reason=deprecation_reason,
            default=default,
            default_factory=default_factory,
            metadata=metadata,
            directives=directives,
            extensions=extensions or [],
            registry_namespace=namespace,
            description=description,
            validation=validation,
        )
        return field(resolver) if resolver else field

    def delete(
        self,
        filter_input: type[BooleanFilterDTO] | None = None,
        resolver: _RESOLVER_TYPE[Any] | None = None,
        *,
        repository_type: AnyRepository | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        graphql_type: Any | None = None,
        extensions: list[FieldExtension] | None = None,
    ) -> Any:
        namespace = self._annotation_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type

        field = StrawchemyDeleteMutationField(
            filter_input,
            config=self.config,
            repository_type=repository_type_,
            python_name=None,
            graphql_name=name,
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=permission_classes or [],
            deprecation_reason=deprecation_reason,
            default=default,
            default_factory=default_factory,
            metadata=metadata,
            directives=directives,
            extensions=extensions or [],
            registry_namespace=namespace,
            description=description,
        )
        return field(resolver) if resolver else field
