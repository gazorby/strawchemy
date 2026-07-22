"""Builder for Strawchemy mutation fields with common configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from strawberry.annotation import StrawberryAnnotation

from strawchemy.schema.mutation.fields import (
    StrawchemyCreateMutationField,
    StrawchemyDeleteMutationField,
    StrawchemyUpdateMutationField,
    StrawchemyUpsertMutationField,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from strawchemy.config.base import StrawchemyConfig
    from strawchemy.schema.factories import DistinctOnEnumFactory
    from strawchemy.schema.factories.inputs import BooleanFilterFactory, OrderByFactory
    from strawchemy.schema.mutation.input import EventRegistry


@dataclass
class MutationFieldBuilder:
    """Builder for Strawchemy mutation fields with common configuration.

    This builder encapsulates the common logic for creating mutation fields
    (create, update, upsert, delete) to eliminate code duplication and provide
    a consistent interface for mutation field creation.
    """

    config: StrawchemyConfig
    registry_namespace_getter: Callable[[], dict[str, Any]]
    order_by_factory: OrderByFactory
    filter_factory: BooleanFilterFactory
    distinct_on_factory: DistinctOnEnumFactory
    event_registry: EventRegistry
    """Shared event registry owned by the Strawchemy instance, reused across mutation requests."""

    def build(
        self,
        field_class: type[
            StrawchemyCreateMutationField
            | StrawchemyUpdateMutationField
            | StrawchemyUpsertMutationField
            | StrawchemyDeleteMutationField
        ],
        resolver: Any | None = None,
        *,
        graphql_type: Any | None = None,
        **field_kwargs: Any,
    ) -> Any:
        """Build a mutation field with common configuration.

        Args:
            field_class: The specific mutation field class to instantiate
                (e.g., StrawchemyCreateMutationField).
            resolver: An optional custom resolver function for the mutation.
            graphql_type: The GraphQL return type of the mutation.
            **field_kwargs: The common ``strawberry.field`` / repository arguments
                (see ``MutationFieldKwargs``) merged with any field-specific arguments
                (e.g., input_type, filter_input, update_fields). ``name`` maps to the
                GraphQL field name.

        Returns:
            A configured mutation field instance, either wrapped with the resolver
            or as a standalone field.
        """
        namespace = self.registry_namespace_getter()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        graphql_name = field_kwargs.pop("name", None)

        # Inject the shared registry only for input mutation fields (create/update/upsert),
        # not for the delete field which shares the `input_type` kwarg name for filter types.
        if issubclass(
            field_class, (StrawchemyCreateMutationField, StrawchemyUpdateMutationField, StrawchemyUpsertMutationField)
        ):
            field_kwargs.setdefault("event_registry", self.event_registry)

        field = field_class(
            config=self.config,
            python_name=None,
            graphql_name=graphql_name,
            type_annotation=type_annotation,
            is_subscription=False,
            registry_namespace=namespace,
            order_by_factory=self.order_by_factory,
            filter_factory=self.filter_factory,
            distinct_on_factory=self.distinct_on_factory,
            **field_kwargs,
        )
        return field(resolver) if resolver else field
