"""Builder for Strawchemy mutation fields with common configuration."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from strawberry.annotation import StrawberryAnnotation

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from strawberry.extensions.field_extension import FieldExtension

    from strawberry import BasePermission
    from strawchemy.config.base import StrawchemyConfig
    from strawchemy.strawberry._field import (
        StrawchemyCreateMutationField,
        StrawchemyDeleteMutationField,
        StrawchemyUpdateMutationField,
        StrawchemyUpsertMutationField,
    )
    from strawchemy.typing import AnyRepository


@dataclass
class MutationFieldBuilder:
    """Builder for Strawchemy mutation fields with common configuration.

    This builder encapsulates the common logic for creating mutation fields
    (create, update, upsert, delete) to eliminate code duplication and provide
    a consistent interface for mutation field creation.
    """

    config: StrawchemyConfig
    registry_namespace_getter: Callable[[], dict[str, Any]]

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
        repository_type: AnyRepository | None = None,
        graphql_type: Any | None = None,
        name: str | None = None,
        description: str | None = None,
        permission_classes: list[type[BasePermission]] | None = None,
        deprecation_reason: str | None = None,
        default: Any = dataclasses.MISSING,
        default_factory: Callable[..., object] | object = dataclasses.MISSING,
        metadata: Mapping[Any, Any] | None = None,
        directives: Sequence[object] = (),
        extensions: list[FieldExtension] | None = None,
        **field_specific_kwargs: Any,
    ) -> Any:
        """Build a mutation field with common configuration.

        Args:
            field_class: The specific mutation field class to instantiate
                (e.g., StrawchemyCreateMutationField).
            resolver: An optional custom resolver function for the mutation.
            repository_type: An optional custom repository class. Defaults to
                the repository configured in StrawchemyConfig.
            graphql_type: The GraphQL return type of the mutation.
            name: The name of the GraphQL mutation field.
            description: The description of the GraphQL mutation field.
            permission_classes: A list of permission classes for the field.
            deprecation_reason: The reason for deprecating the field.
            default: The default value for the field.
            default_factory: A factory function to generate the default value.
            metadata: Additional metadata for the field.
            directives: A sequence of directives for the field.
            extensions: A list of Strawberry FieldExtensions.
            **field_specific_kwargs: Additional keyword arguments specific to
                the field type (e.g., input_type, filter_input, update_fields, etc.).

        Returns:
            A configured mutation field instance, either wrapped with the resolver
            or as a standalone field.
        """
        namespace = self.registry_namespace_getter()
        type_annotation = StrawberryAnnotation.from_annotation(graphql_type, namespace) if graphql_type else None
        repository_type_ = repository_type if repository_type is not None else self.config.repository_type

        field = field_class(
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
            **field_specific_kwargs,
        )
        return field(resolver) if resolver else field
