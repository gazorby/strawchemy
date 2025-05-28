from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from strawchemy.exceptions import StrawchemyError

if TYPE_CHECKING:
    from strawchemy.strawberry.typing import AggregationFunction
    from strawchemy.typing import SupportedDialect


@dataclass(frozen=True)
class DatabaseFeatures(Protocol):
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
    dialect: SupportedDialect = "postgresql"
    supports_distinct_on: bool = True
    supports_lateral: bool = True
    supports_null_ordering: bool = True


@dataclass(frozen=True)
class MySQLFeatures(DatabaseFeatures):
    dialect: SupportedDialect = "mysql"


@dataclass(frozen=True)
class SQLiteFeatures(DatabaseFeatures):
    dialect: SupportedDialect = "sqlite"
    aggregation_functions: set[AggregationFunction] = field(
        default_factory=lambda: {"min", "max", "sum", "avg", "count"}
    )
