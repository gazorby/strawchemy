from typing import Any, Generic, TypeVar, cast, override

from sqlalchemy import ARRAY, ColumnElement, Dialect, Text, type_coerce
from sqlalchemy import cast as sqla_cast
from sqlalchemy.dialects import postgresql as pg
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
        model_attribute: QueryableAttribute[pg.JSON | pg.JSONB] | ColumnElement[pg.JSON | pg.JSONB],
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)
        as_postgres_jsonb = type_coerce(model_attribute, pg.JSONB)

        if "contains" in self.model_fields_set:
            expressions.append(as_postgres_jsonb.contains(self.contains))
        if "contained_in" in self.model_fields_set:
            expressions.append(as_postgres_jsonb.contained_by(self.contained_in))
        if "has_key" in self.model_fields_set:
            expressions.append(as_postgres_jsonb.has_key(self.has_key))
        if "has_key_all" in self.model_fields_set:
            expressions.append(as_postgres_jsonb.has_all(sqla_cast(self.has_key_all, pg.ARRAY(Text))))
        if "has_key_any" in self.model_fields_set:
            expressions.append(as_postgres_jsonb.has_any(sqla_cast(self.has_key_any, pg.ARRAY(Text))))
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
        self, dialect: Dialect, model_attribute: ColumnElement[ARRAY[Any]] | QueryableAttribute[ARRAY[Any]]
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)
        as_postgres_array = type_coerce(model_attribute, pg.ARRAY(cast("ARRAY[Any]", model_attribute.type).item_type))

        if "contains" in self.model_fields_set:
            expressions.append(as_postgres_array.contains(self.contains))
        if "contained_in" in self.model_fields_set:
            expressions.append(as_postgres_array.contained_by(self.contained_in))
        if "overlap" in self.model_fields_set:
            expressions.append(as_postgres_array.overlap(self.overlap))
        return expressions
