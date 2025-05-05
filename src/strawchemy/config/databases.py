from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from strawchemy.exceptions import StrawchemyError

if TYPE_CHECKING:
    from strawchemy.graphql.typing import AggregationFunction
    from strawchemy.typing import SupportedDialect


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
