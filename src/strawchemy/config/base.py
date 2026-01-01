"""Configuration objects for Strawchemy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.repository.strawberry import StrawchemySyncRepository
from strawchemy.utils.strawberry import default_session_getter

if TYPE_CHECKING:
    from strawchemy.repository.typing import AnySessionGetter, FilterMap
    from strawchemy.typing import AnyRepositoryType, SupportedDialect


@dataclass
class StrawchemyConfig:
    """Global configuration for Strawchemy.

    Attributes:
        dialect: The SQLAlchemy dialect being used.
        session_getter: Function to retrieve SQLAlchemy session from strawberry `Info` object.
        auto_snake_case: Automatically convert snake cased names to camel case.
        repository_type: Repository class to use for auto resolvers.
        filter_overrides: Override default filters with custom filters.
        execution_options: SQLAlchemy execution options for strawberry operations.
        pagination_default_limit: Default pagination limit when `pagination=True`.
        pagination: Enable/disable pagination on list resolvers.
        default_id_field_name: Name for primary key fields arguments on primary key resolvers.
        deterministic_ordering: Force deterministic ordering for list resolvers.
        inspector: The SQLAlchemyGraphQLInspector instance.
    """

    dialect: SupportedDialect
    session_getter: AnySessionGetter = default_session_getter
    """Function to retrieve SQLAlchemy session from strawberry `Info` object."""
    auto_snake_case: bool = True
    """Automatically convert snake cased names to camel case"""
    repository_type: AnyRepositoryType = StrawchemySyncRepository
    """Repository class to use for auto resolvers."""
    filter_overrides: FilterMap | None = None
    """Override default filters with custom filters."""
    execution_options: dict[str, Any] | None = None
    """SQLAlchemy execution options for strawberry operations."""
    default_id_field_name: str = "id"
    """Name for primary key fields arguments on primary key resolvers."""
    deterministic_ordering: bool = True
    """Force deterministic ordering for list resolvers."""
    pagination: Literal["all"] | None = None
    """Enable/disable pagination on list resolvers."""
    order_by: Literal["all"] | None = None
    """Enable/disable order by on list resolvers."""
    pagination_default_limit: int = 100
    """Default pagination limit when `pagination=True`."""
    pagination_default_offset: int = 0
    """Default pagination offset when `pagination=True`."""

    inspector: SQLAlchemyGraphQLInspector = field(init=False)

    def __post_init__(self) -> None:
        """Initializes the SQLAlchemyGraphQLInspector after the dataclass is created."""
        self.inspector = SQLAlchemyGraphQLInspector(self.dialect, filter_overrides=self.filter_overrides)
