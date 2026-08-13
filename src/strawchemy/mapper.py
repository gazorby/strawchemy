from __future__ import annotations

import dataclasses
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast, overload

from strawberry.annotation import StrawberryAnnotation
from strawberry.schema.config import StrawberryConfig
from typing_extensions import Unpack

from strawchemy.config.base import StrawchemyConfig
from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend
from strawchemy.dto.base import TYPING_NS
from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO, MappedStrawberryGraphQLDTO, OrderByDTO, OrderByEnum
from strawchemy.dto.utils import read_all_config
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.schema.factories import (
    AggregateFilterFactory,
    AggregateRootTypeFactory,
    BooleanFilterFactory,
    DistinctOnEnumFactory,
    EnumBackend,
    EnumFactory,
    MutationInputFactory,
    ObjectTypeFactory,
    OrderByFactory,
    UpsertConflictEnumBackend,
    UpsertConflictEnumFactory,
)
from strawchemy.schema.field import MutationFieldKwargs, OutputFieldKwargs, StrawberryFieldKwargs, StrawchemyField
from strawchemy.schema.filters.fields import VALID_JOINS, FilterFieldMarker
from strawchemy.schema.mutation import types as mutation_types
from strawchemy.schema.mutation.field_builder import MutationFieldBuilder
from strawchemy.schema.mutation.fields import (
    StrawchemyCreateMutationField,
    StrawchemyDeleteMutationField,
    StrawchemyUpdateMutationField,
    StrawchemyUpsertMutationField,
)
from strawchemy.schema.mutation.input import EventRegistry
from strawchemy.utils.registry import StrawberryRegistry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import DeclarativeBase
    from strawberry.types.arguments import StrawberryArgument

    from strawchemy.dto.types import FieldSpec
    from strawchemy.repository.typing import QueryHookCallable
    from strawchemy.schema.filters.fields import CustomFilterApply, JoinStrategy
    from strawchemy.schema.pagination import DefaultOffsetPagination
    from strawchemy.transpiler.hook import QueryHook
    from strawchemy.typing import (
        AnyRepositoryType,
        FilterStatementCallable,
        MappedGraphQLDTO,
        OrderByExpr,
        SupportedDialect,
    )
    from strawchemy.validation.base import ValidationProtocol
    from strawchemy.validation.pydantic import PydanticMapper

T = TypeVar("T", bound="DeclarativeBase")

__all__ = ("Strawchemy",)


class Strawchemy:
    """Main entry point for integrating SQLAlchemy models with Strawberry GraphQL.

    This class provides a cohesive interface to generate Strawberry GraphQL types,
    inputs, filters, and fields based on SQLAlchemy models. It manages configuration,
    type registration, and various factories for DTO generation.

    Attributes:
        config (StrawchemyConfig): The configuration object for Strawchemy.
        registry (StrawberryRegistry): The registry for Strawberry types.
        filter: Factory for creating boolean filter input types.
        aggregate_filter: Factory for creating aggregate filter input types.
        distinct_on: Decorator for creating distinct_on enum types.
        input: Factory for creating general input types.
        create_input: Factory for creating input types for create mutations.
        pk_update_input: Factory for creating input types for update-by-PK mutations.
        filter_update_input: Factory for creating input types for update-by-filter mutations.
        order: Factory for creating order_by input types.
        type: Factory for creating Strawberry output types.
        aggregate: Factory for creating aggregation root types.
        upsert_update_fields: Factory for creating enum DTOs for upsert update fields.
        upsert_conflict_fields: Factory for creating enum DTOs for upsert conflict fields.
        pydantic (PydanticMapper): A mapper for generating Pydantic models.
    """

    _types_namespace: ClassVar[dict[str, Any]] = TYPING_NS | vars(mutation_types)

    def __init__(
        self,
        config: StrawchemyConfig | SupportedDialect,
        strawberry_config: StrawberryConfig | None = None,
    ) -> None:
        """Initializes the Strawchemy instance.

        Sets up the configuration, registry, and various DTO factories
        required for type and field generation.

        Args:
            config: A StrawchemyConfig instance or a supported dialect string
                    (e.g., "postgresql", "mysql") to initialize a default config.
            strawberry_config: A StrawberryConfig instance to initialize the registry.
                If not provided, a default StrawberryConfig will be used.
        """
        self.config = StrawchemyConfig(cast("SupportedDialect", config)) if isinstance(config, str) else config
        self.registry = StrawberryRegistry(strawberry_config or StrawberryConfig())
        self._event_registry = EventRegistry()

        strawberry_backend = StrawberrryDTOBackend(
            MappedStrawberryGraphQLDTO, auto_is_type_of=self.config.auto_is_type_of
        )
        enum_backend = EnumBackend(self.config.auto_snake_case)
        upsert_conflict_fields_enum_backend = UpsertConflictEnumBackend(
            self.config.inspector, self.config.auto_snake_case
        )

        self.aggregate_filter_factory = AggregateFilterFactory(self)
        self.order_by_factory = OrderByFactory(self)
        self.distinct_on_enum_factory = DistinctOnEnumFactory(self)
        self.type_factory = ObjectTypeFactory(
            self,
            strawberry_backend,
            order_by_factory=self.order_by_factory,
            distinct_on_factory=self.distinct_on_enum_factory,
        )
        self.input_factory = MutationInputFactory(self, strawberry_backend)
        self.aggregation_factory = AggregateRootTypeFactory(self, strawberry_backend, type_factory=self.type_factory)
        self.enum_factory = EnumFactory(self, enum_backend)
        self.filter_factory = BooleanFilterFactory(self, aggregate_filter_factory=self.aggregate_filter_factory)
        self.upsert_conflict_factory = UpsertConflictEnumFactory(self, upsert_conflict_fields_enum_backend)
        self._mutation_builder = MutationFieldBuilder(
            config=self.config,
            registry_namespace_getter=self._annotation_namespace,
            order_by_factory=self.order_by_factory,
            filter_factory=self.filter_factory,
            distinct_on_factory=self.distinct_on_enum_factory,
            event_registry=self._event_registry,
        )

        # Decorators
        self.filter = self.filter_factory.input
        self.aggregate_filter = partial(self.aggregate_filter_factory.input, mode="aggregate_filter")
        self.distinct_on = self.distinct_on_enum_factory.decorator
        self.input = self.input_factory.input
        self.create_input = partial(self.input_factory.input, mode="create_input")
        self.pk_update_input = partial(self.input_factory.input, mode="update_by_pk_input")
        self.filter_update_input = partial(self.input_factory.input, mode="update_by_filter_input")
        self.order = partial(self.order_by_factory.input, mode="order_by")
        self.type = self.type_factory.type
        self.aggregate = partial(self.aggregation_factory.type, mode="aggregate_type")
        self.upsert_update_fields = self.enum_factory.input
        self.upsert_conflict_fields = self.upsert_conflict_factory.input

        # Register common types
        self.registry.register_enum(OrderByEnum, dto_config=read_all_config)

    def _annotation_namespace(self) -> dict[str, Any]:
        """Provides the namespace for Strawberry annotations.

        Combines the registry's 'object' namespace with internal Strawchemy types.

        Returns:
            A dictionary representing the annotation namespace.
        """
        return self.registry.namespace("object") | self._types_namespace

    @cached_property
    def pydantic(self) -> PydanticMapper:
        """Provides access to a PydanticMapper instance.

        This mapper is used for generating Pydantic models corresponding
        to the SQLAlchemy models and Strawberry types.

        Returns:
            An instance of PydanticMapper.
        """
        from strawchemy.validation.pydantic import PydanticMapper  # noqa: PLC0415

        return PydanticMapper(self)

    @overload
    def field(
        self,
        resolver: Any,
        *,
        filter_input: type[BooleanFilterDTO] | bool | None = None,
        order_by_input: FieldSpec | type[OrderByDTO] | None = None,
        default_order_by: Sequence[OrderByExpr] | OrderByExpr | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        distinct_on: FieldSpec | type[EnumDTO] | None = None,
        arguments: list[StrawberryArgument] | None = None,
        model_field: str | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHook[Any] | Sequence[QueryHook[Any]] | None = None,
        repository_type: AnyRepositoryType | None = None,
        root_field: bool = True,
        **field_kwargs: Unpack[OutputFieldKwargs],
    ) -> StrawchemyField: ...

    @overload
    def field(
        self,
        *,
        filter_input: type[BooleanFilterDTO] | bool | None = None,
        order_by_input: FieldSpec | type[OrderByDTO] | None = None,
        default_order_by: Sequence[OrderByExpr] | OrderByExpr | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        distinct_on: FieldSpec | type[EnumDTO] | None = None,
        arguments: list[StrawberryArgument] | None = None,
        model_field: str | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHookCallable[Any] | Sequence[QueryHookCallable[Any]] | None = None,
        repository_type: AnyRepositoryType | None = None,
        root_field: bool = True,
        **field_kwargs: Unpack[OutputFieldKwargs],
    ) -> Any: ...

    def field(
        self,
        resolver: Any | None = None,
        *,
        filter_input: type[BooleanFilterDTO] | bool | None = None,
        order_by_input: FieldSpec | type[OrderByDTO] | None = None,
        default_order_by: Sequence[OrderByExpr] | OrderByExpr | None = None,
        pagination: bool | DefaultOffsetPagination | None = None,
        distinct_on: FieldSpec | type[EnumDTO] | None = None,
        arguments: list[StrawberryArgument] | None = None,
        model_field: str | None = None,
        id_field_name: str | None = None,
        root_aggregations: bool = False,
        filter_statement: FilterStatementCallable | None = None,
        execution_options: dict[str, Any] | None = None,
        query_hook: QueryHookCallable[Any] | Sequence[QueryHookCallable[Any]] | None = None,
        repository_type: AnyRepositoryType | None = None,
        root_field: bool = True,
        **field_kwargs: Unpack[OutputFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL field with enhanced SQLAlchemy capabilities.

        This method extends the standard Strawberry field creation by integrating
        SQLAlchemy-specific features like automatic filtering, ordering, pagination,
        and aggregations based on SQLAlchemy models.

        Args:
            resolver: The resolver function for the field. If not provided,
                Strawchemy will attempt to generate one based on the model.
            filter_input: The input type for filtering results.
            order_by_input: The input type for ordering results.
            default_order_by: Default ordering for a list field as one or more SQLAlchemy
                column ordering expressions (e.g. ``Model.name.asc()``). Applied only when
                the client supplies no ``order_by``. Overrides ``deterministic_ordering``:
                when set, an ordering is always emitted; the primary-key tiebreaker is still
                appended when ``deterministic_ordering`` is True.
            distinct_on: The enum type for 'distinct on' clauses (PostgreSQL).
            pagination: Enables pagination for the field. Can be True for default
                offset pagination or a DefaultOffsetPagination instance for customization.
            arguments: A list of additional StrawberryArgument instances for the field.
            model_field: Name of the model attribute this field maps to. Lets a
                schema field use a different name than the underlying model field.
                Raises StrawchemyFieldError at decoration time if the named model
                field does not exist.
            id_field_name: The name of the ID field, used for certain operations.
            root_aggregations: If True, enables root-level aggregations for the field.
            filter_statement: A callable to generate a filter statement for the query.
            execution_options: SQLAlchemy execution options for the query.
            query_hook: A callable or sequence of callables to modify the SQLAlchemy query.
            repository_type: A custom strawberry class for data fetching logic.
            root_field: Indicates if this is a root-level field.
            **field_kwargs: ``strawberry.field`` arguments forwarded to the generated field
                (see ``OutputFieldKwargs``). ``name`` maps to the GraphQL field name.

        Returns:
            A StrawchemyField instance, which is a specialized StrawberryField.
        """
        namespace = self._annotation_namespace()
        graphql_type = field_kwargs.get("graphql_type")
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None

        if model_field is not None:
            root_field = False

        field = StrawchemyField(
            config=self.config,
            repository_type=repository_type,
            root_field=root_field,
            filter_statement=filter_statement,
            execution_options=execution_options,
            filter_type=filter_input,
            order_by=order_by_input,
            default_order_by=default_order_by,
            pagination=pagination,
            id_field_name=id_field_name,
            distinct_on=distinct_on,
            root_aggregations=root_aggregations,
            query_hook=query_hook,
            model_field=model_field,
            python_name=None,
            graphql_name=field_kwargs.get("name"),
            type_annotation=type_annotation,
            is_subscription=False,
            permission_classes=field_kwargs.get("permission_classes") or [],
            deprecation_reason=field_kwargs.get("deprecation_reason"),
            default=field_kwargs.get("default", dataclasses.MISSING),
            default_factory=field_kwargs.get("default_factory", dataclasses.MISSING),
            metadata=field_kwargs.get("metadata"),
            directives=field_kwargs.get("directives", ()),
            extensions=field_kwargs.get("extensions") or [],
            registry_namespace=namespace,
            description=field_kwargs.get("description"),
            arguments=arguments,
            order_by_factory=self.order_by_factory,
            filter_factory=self.filter_factory,
            distinct_on_factory=self.distinct_on_enum_factory,
        )
        return field(resolver) if resolver else field

    def filter_field(
        self,
        *,
        ops: Sequence[str] | None = None,
        apply: CustomFilterApply | None = None,
        join: JoinStrategy = "exists",
        **field_kwargs: Unpack[StrawberryFieldKwargs],
    ) -> Any:
        """Declares a fine-grained filter field default.

        The field's annotation supplies the comparison data type. With ``ops`` the field exposes
        only those GraphQL operators; with ``apply`` it becomes a custom virtual scalar input;
        with neither it force-includes the column's full default comparison.

        Args:
            ops: GraphQL operator names to expose (restricted field). Mutually exclusive with ``apply``.
            apply: Custom filter callable ``(statement, value, *, dialect, model)`` returning a
                mutated ``Select``.
            join: Fold-back strategy when ``apply`` is set (``"exists"`` or ``"in"``).
            **field_kwargs: ``strawberry.field`` arguments applied to the generated GraphQL field
                (``name``, ``description``, ``metadata``, ``deprecation_reason``, ``directives``,
                ``graphql_type``).

        Returns:
            A ``FilterFieldMarker`` consumed by the filter factory. Typed ``Any`` so it can sit as
            a default under any annotation.

        Raises:
            StrawchemyFieldError: If ``ops`` and ``apply`` are both given, or ``join`` is unsupported.
        """
        if ops is not None and apply is not None:
            msg = "filter_field() arguments 'ops' and 'apply' are mutually exclusive"
            raise StrawchemyFieldError(msg)
        if join not in VALID_JOINS:
            msg = f"Invalid join strategy {join!r}; expected one of {sorted(VALID_JOINS)}"
            raise StrawchemyFieldError(msg)
        return FilterFieldMarker(
            ops=tuple(ops) if ops is not None else None, apply=apply, join=join, field_kwargs=field_kwargs
        )

    def create(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        resolver: Any | None = None,
        *,
        validation: ValidationProtocol[T] | None = None,
        **field_kwargs: Unpack[MutationFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL mutation field for creating new model instances.

        This method generates a mutation field that handles the creation of
        SQLAlchemy model instances based on the provided input type. It integrates
        with Strawchemy's strawberry system for data persistence and allows for
        custom validation.

        Args:
            input_type: The Strawberry input type representing the data for creating
                a new model instance. This should be a `MappedGraphQLDTO`.
            resolver: An optional custom resolver function for the mutation. If not
                provided, Strawchemy will use a default resolver.
            validation: An optional validation protocol instance to validate
                the input data before creation.
            **field_kwargs: Common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``); ``graphql_type`` sets the mutation
                return type.

        Returns:
            A `StrawchemyCreateMutationField` instance, which is a specialized
            StrawberryField configured for create mutations.
        """
        return self._mutation_builder.build(
            StrawchemyCreateMutationField,
            resolver,
            input_type=input_type,
            validation=validation,
            **field_kwargs,
        )

    def upsert(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        update_fields: type[EnumDTO],
        conflict_fields: type[EnumDTO],
        resolver: Any | None = None,
        *,
        validation: ValidationProtocol[T] | None = None,
        **field_kwargs: Unpack[MutationFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL mutation field for upserting model instances.

        This method generates a mutation field that handles the "upsert"
        (update or insert) of SQLAlchemy model instances. It uses the provided
        input type, update fields enum, and conflict fields enum to determine
        the behavior on conflict. It integrates with Strawchemy's strawberry
        system and allows for custom validation.

        Args:
            input_type: The Strawberry input type representing the data for
                the upsert operation. This should be a `MappedGraphQLDTO`.
            update_fields: An `EnumDTO` specifying which fields to update if a
                conflict occurs and an update is performed.
            conflict_fields: An `EnumDTO` specifying the fields to use for
                conflict detection (e.g., primary key or unique constraints).
            resolver: An optional custom resolver function for the mutation. If not
                provided, Strawchemy will use a default resolver.
            validation: An optional validation protocol instance to validate
                the input data before the upsert operation.
            **field_kwargs: Common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``); ``graphql_type`` sets the mutation
                return type.

        Returns:
            A `StrawchemyUpsertMutationField` instance, which is a specialized
            StrawberryField configured for upsert mutations.
        """
        return self._mutation_builder.build(
            StrawchemyUpsertMutationField,
            resolver,
            input_type=input_type,
            update_fields_enum=update_fields,
            conflict_fields_enum=conflict_fields,
            validation=validation,
            **field_kwargs,
        )

    def update(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        filter_input: type[BooleanFilterDTO],
        resolver: Any | None = None,
        *,
        validation: ValidationProtocol[T] | None = None,
        **field_kwargs: Unpack[MutationFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL mutation field for updating model instances.

        This method generates a mutation field that handles updating existing
        SQLAlchemy model instances based on filter criteria. It uses the provided
        input type for the update data and a filter input type to specify which
        records to update. It integrates with Strawchemy's strawberry system and
        allows for custom validation.

        Args:
            input_type: The Strawberry input type representing the data to update
                on the model instances. This should be a `MappedGraphQLDTO`.
            filter_input: The Strawberry input type used to filter which model
                instances should be updated. This should be a `BooleanFilterDTO`.
            resolver: An optional custom resolver function for the mutation. If not
                provided, Strawchemy will use a default resolver.
            validation: An optional validation protocol instance to validate
                the input data before the update operation.
            **field_kwargs: Common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``); ``graphql_type`` sets the mutation
                return type.

        Returns:
            A `StrawchemyUpdateMutationField` instance, which is a specialized
            StrawberryField configured for update mutations.
        """
        return self._mutation_builder.build(
            StrawchemyUpdateMutationField,
            resolver,
            input_type=input_type,
            filter_type=filter_input,
            validation=validation,
            **field_kwargs,
        )

    def update_by_ids(
        self,
        input_type: type[MappedGraphQLDTO[T]],
        resolver: Any | None = None,
        *,
        validation: ValidationProtocol[T] | None = None,
        **field_kwargs: Unpack[MutationFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL mutation field for updating model instances by IDs.

        This method generates a mutation field that handles updating existing
        SQLAlchemy model instances based on their primary key(s). The input type
        should typically include the ID(s) of the record(s) to update and the
        data to apply. It integrates with Strawchemy's strawberry system and
        allows for custom validation.

        Args:
            input_type: The Strawberry input type representing the data for updating
                model instances. This should be a `MappedGraphQLDTO`, usually
                generated by `pk_update_input`, which includes primary key fields.
            resolver: An optional custom resolver function for the mutation. If not
                provided, Strawchemy will use a default resolver.
            validation: An optional validation protocol instance to validate
                the input data before the update operation.
            **field_kwargs: Common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``); ``graphql_type`` sets the mutation
                return type.

        Returns:
            A `StrawchemyUpdateMutationField` instance, specialized for updates
            by ID.
        """
        return self._mutation_builder.build(
            StrawchemyUpdateMutationField,
            resolver,
            input_type=input_type,
            validation=validation,
            **field_kwargs,
        )

    def delete(
        self,
        filter_input: type[BooleanFilterDTO] | None = None,
        resolver: Any | None = None,
        **field_kwargs: Unpack[MutationFieldKwargs],
    ) -> Any:
        """Creates a Strawberry GraphQL mutation field for deleting model instances.

        This method generates a mutation field that handles the deletion of
        SQLAlchemy model instances. Deletion can be based on filter criteria
        provided via `filter_input` or by ID if the `filter_input` is structured
        to accept primary key(s). It integrates with Strawchemy's strawberry
        system for data persistence.

        Args:
            filter_input: The Strawberry input type used to filter which model
                instances should be deleted. This should be a `BooleanFilterDTO`.
                If deleting by ID, this DTO should contain the ID field(s).
                If None, the mutation might be configured to delete a single
                record based on an ID passed directly (implementation dependent).
            resolver: An optional custom resolver function for the mutation. If not
                provided, Strawchemy will use a default resolver.
            **field_kwargs: Common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``); ``graphql_type`` sets the mutation
                return type.

        Returns:
            A `StrawchemyDeleteMutationField` instance, which is a specialized
            StrawberryField configured for delete mutations.
        """
        return self._mutation_builder.build(
            StrawchemyDeleteMutationField,
            resolver,
            input_type=filter_input,
            **field_kwargs,
        )
