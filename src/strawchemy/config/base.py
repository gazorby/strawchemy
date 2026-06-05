"""Configuration objects for Strawchemy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from strawchemy.dto import Purpose
from strawchemy.dto.inspectors import SQLAlchemyGraphQLInspector
from strawchemy.dto.types import DTOConfig, FieldSpec
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
    strict: bool = True
    """When False, silently skip (and warn about) model columns whose type hint has no GraphQL
    mapping, instead of failing the schema build. Explicit `type_overrides` are always honored.
    Note: types mapped only via `strawberry.Schema(scalar_overrides=...)` are not visible here;
    force them with `type_overrides=` instead."""
    auto_is_type_of: bool = True
    """Auto-generate is_type_of (an isinstance check against the model) on mapped
    output object types so they work as GraphQL Union / interface members without
    boilerplate. A user-defined is_type_of on the decorated class is always
    respected. Set to False to disable globally."""
    include: FieldSpec = "all"
    """Globally included fields."""
    exclude: FieldSpec | None = None
    """Globally included fields."""
    pagination: FieldSpec | None = None
    """Enable/disable pagination on list resolvers."""
    order_by: FieldSpec | None = None
    """Enable/disable order by on list resolvers."""
    distinct_on: FieldSpec | None = None
    """Enable/disable order by on list resolvers."""
    pagination_default_limit: int = 100
    """Default pagination limit when `pagination=True`."""
    pagination_default_offset: int = 0
    """Default pagination offset when `pagination=True`."""

    inspector: SQLAlchemyGraphQLInspector = field(init=False)

    def __post_init__(self) -> None:
        """Initializes the SQLAlchemyGraphQLInspector after the dataclass is created."""
        self.inspector = SQLAlchemyGraphQLInspector(self.dialect, filter_overrides=self.filter_overrides)

    @property
    def field_config(self) -> DTOConfig:
        return DTOConfig(purpose=Purpose.READ, global_include=self.include, global_exclude=self.exclude or set())

    @property
    def order_config(self) -> DTOConfig:
        return DTOConfig.from_include(self.order_by)

    @property
    def distinct_on_config(self) -> DTOConfig:
        return DTOConfig.from_include(self.distinct_on)

    @property
    def pagination_config(self) -> DTOConfig:
        return DTOConfig.from_include(self.pagination)
