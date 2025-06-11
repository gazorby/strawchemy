"""Database feature configurations for different SQL dialects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from strawchemy.exceptions import StrawchemyError

if TYPE_CHECKING:
    from strawchemy.strawberry.typing import AggregationFunction
    from strawchemy.typing import SupportedDialect


@dataclass(frozen=True)
class DatabaseFeatures(Protocol):
    """Defines a protocol for database-specific features.

    Attributes:
        dialect: The SQL dialect supported by these features.
        supports_lateral: Whether the database supports LATERAL joins.
        supports_distinct_on: Whether the database supports DISTINCT ON.
        supports_json: Whether the database supports JSON operations.
        supports_null_ordering: Whether the database supports NULLS FIRST/LAST ordering.
        aggregation_functions: A set of supported aggregation function names.
    """

    dialect: SupportedDialect
    supports_lateral: bool = False
    supports_distinct_on: bool = False
    supports_json: bool = True
    supports_null_ordering: bool = False
    aggregation_functions: set[AggregationFunction] = field(
        default_factory=lambda: {
            "min",
            "max",
            "sum",
            "avg",
            "count",
            "stddev_samp",
            "stddev_pop",
            "var_samp",
            "var_pop",
        }
    )

    @classmethod
    def new(cls, dialect: SupportedDialect) -> DatabaseFeatures:
        """Factory method to create a DatabaseFeatures instance for the given dialect.

        Args:
            dialect: The SQL dialect.

        Returns:
            A DatabaseFeatures instance for the specified dialect.

        Raises:
            StrawchemyError: If the dialect is unsupported.
        """
        if dialect == "postgresql":
            return PostgresFeatures()
        if dialect == "mysql":
            return MySQLFeatures()
        if dialect == "sqlite":
            return SQLiteFeatures()
        msg = "Unsupported dialect"
        raise StrawchemyError(msg)


@dataclass(frozen=True)
class PostgresFeatures(DatabaseFeatures):
    """Database features specific to PostgreSQL."""

    dialect: SupportedDialect = "postgresql"
    supports_distinct_on: bool = True
    supports_lateral: bool = True
    supports_null_ordering: bool = True


@dataclass(frozen=True)
class MySQLFeatures(DatabaseFeatures):
    """Database features specific to MySQL."""

    dialect: SupportedDialect = "mysql"


@dataclass(frozen=True)
class SQLiteFeatures(DatabaseFeatures):
    """Database features specific to SQLite."""

    dialect: SupportedDialect = "sqlite"
    aggregation_functions: set[AggregationFunction] = field(
        default_factory=lambda: {"min", "max", "sum", "avg", "count"}
    )
