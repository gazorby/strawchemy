"""Factory container for organizing Strawchemy DTO factories."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strawchemy.mapper import Strawchemy
    from strawchemy.strawberry.factories.aggregations import EnumDTOFactory
    from strawchemy.strawberry.factories.inputs import AggregateFilterDTOFactory, BooleanFilterDTOFactory
    from strawchemy.strawberry.factories.types import (
        DistinctOnFieldsDTOFactory,
        InputFactory,
        OrderByDTOFactory,
        RootAggregateTypeDTOFactory,
        TypeDTOFactory,
        UpsertConflictFieldsDTOFactory,
    )


@dataclass
class StrawchemyFactories:
    """Container for all Strawchemy DTO factories.

    This class encapsulates the initialization and management of all factory
    instances used by Strawchemy, providing a cleaner separation of concerns
    and easier testing.

    Attributes:
        aggregate_filter: Factory for aggregate filter DTOs.
        order_by: Factory for order by DTOs.
        distinct_on_enum: Factory for distinct on enum DTOs.
        type_factory: Factory for output type DTOs.
        input_factory: Factory for input type DTOs.
        aggregation: Factory for root aggregate type DTOs.
        enum_factory: Factory for enum DTOs.
        filter_factory: Factory for boolean filter DTOs.
        upsert_conflict: Factory for upsert conflict fields DTOs.
    """

    aggregate_filter: AggregateFilterDTOFactory
    order_by: OrderByDTOFactory
    distinct_on_enum: DistinctOnFieldsDTOFactory
    type_factory: TypeDTOFactory  # type: ignore[type-arg]
    input_factory: InputFactory  # type: ignore[type-arg]
    aggregation: RootAggregateTypeDTOFactory  # type: ignore[type-arg]
    enum_factory: EnumDTOFactory
    filter_factory: BooleanFilterDTOFactory
    upsert_conflict: UpsertConflictFieldsDTOFactory

    @classmethod
    def create(cls, mapper: Strawchemy) -> StrawchemyFactories:
        """Create all factories with proper dependencies.

        Args:
            mapper: The Strawchemy instance that will own these factories.

        Returns:
            A StrawchemyFactories instance with all factories initialized.
        """
        # Imports inside method to avoid circular dependencies at module load time
        from strawchemy.dto.backend.strawberry import StrawberrryDTOBackend  # noqa: PLC0415
        from strawchemy.strawberry.dto import MappedStrawberryGraphQLDTO  # noqa: PLC0415
        from strawchemy.strawberry.factories.aggregations import EnumDTOFactory  # noqa: PLC0415
        from strawchemy.strawberry.factories.enum import (  # noqa: PLC0415
            EnumDTOBackend,
            UpsertConflictFieldsEnumDTOBackend,
        )
        from strawchemy.strawberry.factories.inputs import (  # noqa: PLC0415
            AggregateFilterDTOFactory,
            BooleanFilterDTOFactory,
        )
        from strawchemy.strawberry.factories.types import (  # noqa: PLC0415
            DistinctOnFieldsDTOFactory,
            InputFactory,
            OrderByDTOFactory,
            RootAggregateTypeDTOFactory,
            TypeDTOFactory,
            UpsertConflictFieldsDTOFactory,
        )

        config = mapper.config

        # Create backend instances
        strawberry_backend = StrawberrryDTOBackend(MappedStrawberryGraphQLDTO)
        enum_backend = EnumDTOBackend(config.auto_snake_case)
        upsert_conflict_fields_enum_backend = UpsertConflictFieldsEnumDTOBackend(
            config.inspector, config.auto_snake_case
        )

        # Create factory instances
        aggregate_filter = AggregateFilterDTOFactory(mapper)
        order_by = OrderByDTOFactory(mapper)
        distinct_on_enum = DistinctOnFieldsDTOFactory(config.inspector)
        type_factory = TypeDTOFactory(mapper, strawberry_backend, order_by_factory=order_by)
        input_factory = InputFactory(mapper, strawberry_backend)
        aggregation = RootAggregateTypeDTOFactory(mapper, strawberry_backend, type_factory=type_factory)
        enum_factory = EnumDTOFactory(config.inspector, enum_backend)
        filter_factory = BooleanFilterDTOFactory(mapper, aggregate_filter_factory=aggregate_filter)
        upsert_conflict = UpsertConflictFieldsDTOFactory(config.inspector, upsert_conflict_fields_enum_backend)

        return cls(
            aggregate_filter=aggregate_filter,
            order_by=order_by,
            distinct_on_enum=distinct_on_enum,
            type_factory=type_factory,
            input_factory=input_factory,
            aggregation=aggregation,
            enum_factory=enum_factory,
            filter_factory=filter_factory,
            upsert_conflict=upsert_conflict,
        )

    def create_public_api(self) -> dict[str, Any]:
        """Create the public API mappings for factory methods.

        Returns:
            A dictionary mapping public API names to factory methods.
        """
        return {
            "filter": self.filter_factory.input,
            "aggregate_filter": partial(self.aggregate_filter.input, mode="aggregate_filter"),
            "distinct_on": self.distinct_on_enum.decorator,
            "input": self.input_factory.input,
            "create_input": partial(self.input_factory.input, mode="create_input"),
            "pk_update_input": partial(self.input_factory.input, mode="update_by_pk_input"),
            "filter_update_input": partial(self.input_factory.input, mode="update_by_filter_input"),
            "order": partial(self.order_by.input, mode="order_by"),
            "type": self.type_factory.type,
            "aggregate": partial(self.aggregation.type, mode="aggregate_type"),
            "upsert_update_fields": self.enum_factory.input,
            "upsert_conflict_fields": self.upsert_conflict.input,
        }
