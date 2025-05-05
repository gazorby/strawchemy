from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from strawchemy.exceptions import StrawchemyError

from .sqlalchemy import SQLAlchemyGraphQLInspector
from .strawberry import default_session_getter
from .strawberry.repository import StrawchemySyncRepository

if TYPE_CHECKING:
    from typing import Any

    from strawchemy.graphql.typing import AggregationFunction

    from .graphql.inspector import GraphQLInspectorProtocol
    from .sqlalchemy.typing import FilterMap
    from .strawberry.typing import AnySessionGetter
    from .typing import AnyRepository, SupportedDialect


class DatabaseFeatures(Protocol):
    dialect: SupportedDialect
    aggregation_functions: set[AggregationFunction]
    supports_lateral: bool

    @classmethod
    def new(cls, dialect: SupportedDialect) -> DatabaseFeatures:
        if dialect == "postgresql":
            return PostgresFeatures()
        msg = "Unsupported dialect"
        raise StrawchemyError(msg)


@dataclass(frozen=True)
class PostgresFeatures(DatabaseFeatures):
    dialect: SupportedDialect = "postgresql"
    supports_lateral: bool = True
    aggregation_functions: set[AggregationFunction] = field(
        default_factory=lambda: {
            "min",
            "max",
            "sum",
            "avg",
            "count",
            "stddev",
            "stddev_samp",
            "stddev_pop",
            "variance",
            "var_samp",
            "var_pop",
        }
    )


@dataclass
class StrawchemyConfig:
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
    dialect: SupportedDialect = "postgresql"

    inspector: GraphQLInspectorProtocol[Any, Any] = field(init=False)
    database_features: DatabaseFeatures = field(init=False)

    def __post_init__(self) -> None:
        if self.dialect == "postgresql":
            self.database_features = PostgresFeatures()
        self.inspector = SQLAlchemyGraphQLInspector(self.database_features, filter_overrides=self.filter_overrides)
