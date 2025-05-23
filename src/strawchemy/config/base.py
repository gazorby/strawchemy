from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from strawchemy.sqlalchemy.inspector import SQLAlchemyGraphQLInspector
from strawchemy.strawberry import default_session_getter
from strawchemy.strawberry.repository import StrawchemySyncRepository

if TYPE_CHECKING:
    from typing import Any

    from strawchemy.sqlalchemy.typing import FilterMap
    from strawchemy.strawberry.typing import AnySessionGetter
    from strawchemy.typing import AnyRepository, SupportedDialect


@dataclass
class StrawchemyConfig:
    dialect: SupportedDialect
    session_getter: AnySessionGetter = default_session_getter
    """Function to retrieve SQLAlchemy session from strawberry `Info` object."""
    auto_snake_case: bool = True
    """Automatically convert snake cased names to camel case"""
    repository_type: AnyRepository = StrawchemySyncRepository
    """Repository class to use for auto resolvers."""
    filter_overrides: FilterMap | None = None
    """Override default filters with custom filters."""
    execution_options: dict[str, Any] | None = None
    """SQLAlchemy execution options for repository operations."""
    pagination_default_limit: int = 100
    """Default pagination limit when `pagination=True`."""
    pagination: bool = False
    """Enable/disable pagination on list resolvers."""
    default_id_field_name: str = "id"
    """Name for primary key fields arguments on primary key resolvers."""
    deterministic_ordering: bool = True
    """Force deterministic ordering for list resolvers."""

    inspector: SQLAlchemyGraphQLInspector = field(init=False)

    def __post_init__(self) -> None:
        self.inspector = SQLAlchemyGraphQLInspector(self.dialect, filter_overrides=self.filter_overrides)
