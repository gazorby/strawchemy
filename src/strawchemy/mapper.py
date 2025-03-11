from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

from strawberry.annotation import StrawberryAnnotation
from strawchemy.dto.backend.dataclass import DataclassDTOBackend
from strawchemy.dto.base import ModelFieldT, ModelT

from .config import StrawchemyConfig
from .graphql.dto import EnumDTO, MappedDataclassGraphQLDTO, OrderByEnum
from .graphql.factory import DistinctOnFieldsDTOFactory
from .strawberry import StrawchemyField
from .strawberry.factory import (
    StrawberryAggregateFilterInputFactory,
    StrawberryFilterInputFactory,
    StrawberryOrderByInputFactory,
    StrawberryRegistry,
    StrawberryRootAggregateTypeFactory,
    StrawberryTypeFactory,
)
from .strawberry.inspector import _StrawberryModelInspector
from .types import DefaultOffsetPagination

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from strawberry import BasePermission
    from strawberry.extensions.field_extension import FieldExtension
    from strawberry.types.field import _RESOLVER_TYPE

    from .sqlalchemy.typing import QueryHookCallable
    from .strawberry.typing import FilterStatementCallable
    from .typing import AnyRepository


T = TypeVar("T")

__all__ = ("Strawchemy",)


class Strawchemy(Generic[ModelT, ModelFieldT]):
    def __init__(self, settings: StrawchemyConfig | None = None) -> None:
        dataclass_backend = DataclassDTOBackend(MappedDataclassGraphQLDTO)
        self.settings = settings or StrawchemyConfig()
        self.registry = StrawberryRegistry()
        self.inspector = _StrawberryModelInspector(self.settings.inspector, self.registry)

        self._filter_factory = StrawberryFilterInputFactory(self)
        self._aggregate_filter_factory = StrawberryAggregateFilterInputFactory(self)
        self._order_by_factory = StrawberryOrderByInputFactory(self)
        self._distinct_on_enum_factory = DistinctOnFieldsDTOFactory(self.inspector)
        self._type_factory = StrawberryTypeFactory(self, dataclass_backend)
        self._aggregation_factory = StrawberryRootAggregateTypeFactory(self, dataclass_backend)

        self.filter_input = self._filter_factory.input
        self.aggregate_filter_input = self._aggregate_filter_factory.input
        self.order_by_input = self._order_by_factory.input
        self.distinct_on_enum = self._distinct_on_enum_factory.decorator
        self.input = self._type_factory.input
        self.type = self._type_factory.type
        self.aggregation_type = self._aggregation_factory.type

        # Register common types
        self.registry.register_enum(OrderByEnum, "OrderByEnum")

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
        filter_input: type[Any] | None = None,
        order_by: type[Any] | None = None,
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
    ) -> StrawchemyField[ModelT, ModelFieldT]: ...

    @overload
    def field(
        self,
        *,
        filter_input: type[Any] | None = None,
        order_by: type[Any] | None = None,
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
        filter_input: type[Any] | None = None,
        order_by: type[Any] | None = None,
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
        namespace = self.registry.namespace("object")
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
        if resolver:
            return field(resolver)
        return field
