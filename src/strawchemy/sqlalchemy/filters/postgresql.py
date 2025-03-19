from typing import Any, Generic, TypeVar, override

from sqlalchemy import ColumnElement, Dialect, Text, cast
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.graphql.filters import JSONComparison, PostgresArrayComparison
from strawchemy.sqlalchemy.filters.base import GenericSQLAlchemyFilter

T = TypeVar("T")


class JSONBSQLAlchemyFilter(
    JSONComparison[DeclarativeBase, QueryableAttribute[Any]], GenericSQLAlchemyFilter[dict[str, Any]]
):
    """JSONB SQLAlchemy filter for JSONB comparison operations.

    This class extends GenericSQLAlchemyFilter and adds filtering
    capabilities for contains, contained_in, has_key, has_key_all,
    and has_key_any operations.
    """

    @override
    def to_expressions(
        self,
        dialect: Dialect,
        model_attribute: QueryableAttribute[Any] | ColumnElement[Any],
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)

        if "contains" in self.model_fields_set:
            expressions.append(model_attribute.contains(self.contains))
        if "contained_in" in self.model_fields_set:
            expressions.append(model_attribute.contained_by(self.contained_in))
        if "has_key" in self.model_fields_set:
            expressions.append(model_attribute.has_key(self.has_key))
        if "has_key_all" in self.model_fields_set:
            expressions.append(model_attribute.has_all(cast(self.has_key_all, postgresql.ARRAY(Text))))
        if "has_key_any" in self.model_fields_set:
            expressions.append(model_attribute.has_any(cast(self.has_key_any, postgresql.ARRAY(Text))))
        return expressions


class PostgresArraySQLAlchemyFilter(
    PostgresArrayComparison[T, DeclarativeBase, QueryableAttribute[Any]], GenericSQLAlchemyFilter[T], Generic[T]
):
    """Postgres Array SQLAlchemy filter for array comparison operations.

    This class extends GenericSQLAlchemyFilter and adds filtering
    capabilities for contains, contained_in, and overlap operations.
    """

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[Any] | QueryableAttribute[Any]
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)

        if "contains" in self.model_fields_set:
            expressions.append(model_attribute.contains(self.contains))
        if "contained_in" in self.model_fields_set:
            expressions.append(model_attribute.contained_by(self.contained_in))
        if "overlap" in self.model_fields_set:
            expressions.append(model_attribute.overlap(self.overlap))
        return expressions
