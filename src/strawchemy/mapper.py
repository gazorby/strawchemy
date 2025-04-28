from __future__ import annotations

import dataclasses
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar, overload

from strawberry.annotation import StrawberryAnnotation
from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.backend.pydantic import PydanticDTOBackend

from ._factories import (
    StrawberryRegistry,
    StrawchemyAggregateFilterInputFactory,
    StrawchemyFilterInputFactory,
    StrawchemyInputFactory,
    StrawchemyInputValidationFactory,
    StrawchemyOrderByInputFactory,
    StrawchemyRootAggregateTypeFactory,
    StrawchemyTypeFactory,
)
from .config import StrawchemyConfig
from .graphql.dto import (
    BooleanFilterDTO,
    EnumDTO,
    MappedDataclassGraphQLDTO,
    MappedPydanticGraphQLDTO,
    OrderByDTO,
    OrderByEnum,
)
from .graphql.factories.types import DistinctOnFieldsDTOFactory
from .strawberry import (
    StrawchemyCreateMutationField,
    StrawchemyDeleteMutationField,
    StrawchemyField,
    StrawchemyUpdateMutationField,
    types,
)
from .strawberry.inspector import _StrawberryModelInspector
from .types import DefaultOffsetPagination

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
    from strawberry import BasePermission
    from strawberry.extensions.field_extension import FieldExtension
    from strawberry.types.field import _RESOLVER_TYPE
    from strawchemy.dto.pydantic import MappedPydanticDTO
    from strawchemy.graphql.typing import MappedGraphQLDTO

    from .sqlalchemy.hook import QueryHook
    from .sqlalchemy.typing import QueryHookCallable
    from .strawberry.typing import FilterStatementCallable, StrawchemyTypeFromPydantic
    from .typing import AnyRepository


T = TypeVar("T", bound="DeclarativeBase")

_TYPES_NS = vars(types)

__all__ = ("Strawchemy",)


class _PydanticNamespace:
    def __init__(self, strawchemy: Strawchemy) -> None:
        pydantic_backend = PydanticDTOBackend(MappedPydanticGraphQLDTO)
        self._strawchemy = strawchemy
        self._validation_factory = StrawchemyInputValidationFactory(self._strawchemy, pydantic_backend)

        self.create = partial(self._validation_factory.input, mode="create")
        self.pk_update = partial(self._validation_factory.input, mode="update_by_pk")
        self.filter_update = partial(self._validation_factory.input, mode="update_by_filter")


class Strawchemy:
    def __init__(self, settings: StrawchemyConfig | None = None) -> None:
        dataclass_backend = DataclassDTOBackend(MappedDataclassGraphQLDTO)
        pydantic_backend = PydanticDTOBackend(MappedPydanticGraphQLDTO)

        self.settings = settings or StrawchemyConfig()
        self.registry = StrawberryRegistry()
        self.inspector = _StrawberryModelInspector(self.settings.inspector, self.registry)

        self._aggregate_filter_factory = StrawchemyAggregateFilterInputFactory(self)
        self._filter_factory = StrawchemyFilterInputFactory(
            self, aggregate_filter_factory=self._aggregate_filter_factory
        )
        self._order_by_factory = StrawchemyOrderByInputFactory(self)
        self._distinct_on_enum_factory = DistinctOnFieldsDTOFactory(self.inspector)
        self._type_factory = StrawchemyTypeFactory(self, dataclass_backend, order_by_factory=self._order_by_factory)
        self._input_factory = StrawchemyInputFactory(self, dataclass_backend)
        self._validation_factory = StrawchemyInputValidationFactory(self, pydantic_backend)
        self._aggregation_factory = StrawchemyRootAggregateTypeFactory(
            self, dataclass_backend, type_factory=self._type_factory
        )

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

        self.pydantic = _PydanticNamespace(self)

        # Register common types
        self.registry.register_enum(OrderByEnum, "OrderByEnum")

    def _registry_namespace(self) -> dict[str, Any]:
        return self.registry.namespace("object") | _TYPES_NS

    def clear(self) -> None:
        self.registry.clear()
        for factory in (
            self._filter_factory,
            self._aggregate_filter_factory,
            self._order_by_factory,
            self._distinct_on_enum_factory,
            self._type_factory,
            self._aggregation_factory,
        ):
            factory.clear()

    @overload
    def field(
        self,
        resolver: _RESOLVER_TYPE[Any],
        *,
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
        order_by: type[StrawchemyTypeFromPydantic[OrderByDTO[T, QueryableAttribute[Any]]]] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
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
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
        order_by: type[StrawchemyTypeFromPydantic[OrderByDTO[T, QueryableAttribute[Any]]]] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
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
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
        order_by: type[StrawchemyTypeFromPydantic[OrderByDTO[T, QueryableAttribute[Any]]]] | None = None,
        distinct_on: type[EnumDTO] | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
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
        namespace = self._registry_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.settings.repository_type
        execution_options_ = execution_options if execution_options is not None else self.settings.execution_options
        pagination = (
            DefaultOffsetPagination(limit=self.settings.pagination_default_limit) if pagination is True else pagination
        )
        if pagination is None:
            pagination = self.settings.pagination
        id_field_name = id_field_name or self.settings.default_id_field_name

        field = StrawchemyField(
            repository_type=repository_type_,
            root_field=root_field,
            session_getter=self.settings.session_getter,
            filter_statement=filter_statement,
            execution_options=execution_options_,
            inspector=self.inspector,
            filter_type=filter_input,
            order_by=order_by,
            pagination=pagination,
            id_field_name=id_field_name,
            distinct_on=distinct_on,
            root_aggregations=root_aggregations,
            auto_snake_case=self.settings.auto_snake_case,
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
        validation: type[MappedPydanticDTO[T]] | None = None,
    ) -> Any:
        namespace = self._registry_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.settings.repository_type

        field = StrawchemyCreateMutationField(
            input_type,
            repository_type=repository_type_,
            session_getter=self.settings.session_getter,
            inspector=self.inspector,
            auto_snake_case=self.settings.auto_snake_case,
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
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]],
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
        validation: type[MappedPydanticDTO[T]] | None = None,
    ) -> Any:
        namespace = self._registry_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.settings.repository_type

        field = StrawchemyUpdateMutationField(
            input_type=input_type,
            filter_type=filter_input,
            repository_type=repository_type_,
            session_getter=self.settings.session_getter,
            inspector=self.inspector,
            auto_snake_case=self.settings.auto_snake_case,
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
        validation: type[MappedPydanticDTO[T]] | None = None,
    ) -> Any:
        namespace = self._registry_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.settings.repository_type

        field = StrawchemyUpdateMutationField(
            input_type=input_type,
            repository_type=repository_type_,
            session_getter=self.settings.session_getter,
            inspector=self.inspector,
            auto_snake_case=self.settings.auto_snake_case,
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
        filter_input: type[StrawchemyTypeFromPydantic[BooleanFilterDTO[T, QueryableAttribute[Any]]]] | None = None,
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
        namespace = self._registry_namespace()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.settings.repository_type

        field = StrawchemyDeleteMutationField(
            filter_input,
            repository_type=repository_type_,
            session_getter=self.settings.session_getter,
            inspector=self.inspector,
            auto_snake_case=self.settings.auto_snake_case,
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
