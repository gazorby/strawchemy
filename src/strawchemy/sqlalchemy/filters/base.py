from __future__ import annotations

import abc
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Generic, TypeVar, override

from sqlalchemy import ColumnElement, Dialect, func, not_, null
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute
from strawchemy.graphql.filters import (
    DateComparison,
    GenericComparison,
    GraphQLComparison,
    OrderComparison,
    TextComparison,
    TimeComparison,
    TimeDeltaComparison,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement

__all__ = (
    "BaseDateSQLAlchemyFilter",
    "BaseTimeSQLAlchemyFilter",
    "DateSQLAlchemyFilter",
    "DateTimeSQLAlchemyFilter",
    "GenericSQLAlchemyFilter",
    "OrderSQLAlchemyFilter",
    "TextSQLAlchemyFilter",
    "TimeDeltaSQLAlchemyFilter",
    "TimeSQLAlchemyFilter",
)

T = TypeVar("T")


class SQLAlchemyFilterBase(GraphQLComparison[DeclarativeBase, QueryableAttribute[Any]], abc.ABC):
    @abc.abstractmethod
    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]: ...


class GenericSQLAlchemyFilter(
    SQLAlchemyFilterBase, GenericComparison[T, DeclarativeBase, QueryableAttribute[Any]], Generic[T]
):
    """Generic SQLAlchemy filter for basic comparison operations.

    This class provides filtering capabilities for equality, inequality,
    inclusion, exclusion, and null checks.
    """

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        """Convert filter to SQLAlchemy expressions.

        Args:
            dialect: SQLAlchemy dialect.
            model_attribute: SQLAlchemy model attribute or column element.

        Returns:
            A list of SQLAlchemy boolean expressions.
        """
        expressions: list[ColumnElement[bool]] = []

        if "eq" in self.model_fields_set:
            expressions.append(model_attribute == self.eq)
        if "neq" in self.model_fields_set:
            expressions.append(model_attribute != self.neq)
        if "in_" in self.model_fields_set and self.in_ is not None:
            expressions.append(model_attribute.in_(self.in_))
        if "nin" in self.model_fields_set and self.nin is not None:
            expressions.append(model_attribute.not_in(self.nin))
        if "is_null" in self.model_fields_set and self.is_null is not None:
            expressions.append(model_attribute.is_(null()) if self.is_null else model_attribute.is_not(null()))

        return expressions


class OrderSQLAlchemyFilter(
    OrderComparison[T, DeclarativeBase, QueryableAttribute[Any]], GenericSQLAlchemyFilter[T], Generic[T]
):
    """Order filter for comparison operations on values that can be ordered.

    This class extends GenericSQLAlchemyFilter and adds filtering
    capabilities for greater than, greater than or equal to, less than,
    and less than or equal to operations.
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

        if "gt" in self.model_fields_set:
            expressions.append(model_attribute > self.gt)
        if "gte" in self.model_fields_set:
            expressions.append(model_attribute >= self.gte)
        if "lt" in self.model_fields_set:
            expressions.append(model_attribute < self.lt)
        if "lte" in self.model_fields_set:
            expressions.append(model_attribute <= self.lte)

        return expressions


class TextSQLAlchemyFilter(TextComparison[DeclarativeBase, QueryableAttribute[Any]], OrderSQLAlchemyFilter[str]):
    """Text SQLAlchemy filter for text comparison operations.

    This class extends GenericSQLAlchemyFilter and adds filtering
    capabilities for like, not like, ilike, not ilike, regexp,
    not regexp, startswith, endswith, contains, istartswith,
    iendswith, and icontains operations.
    """

    def _like_expressions(
        self, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if "like" in self.model_fields_set:
            expressions.append(model_attribute.like(self.like))
        if "nlike" in self.model_fields_set:
            expressions.append(model_attribute.not_like(self.nlike))
        if "ilike" in self.model_fields_set:
            expressions.append(model_attribute.ilike(self.ilike))
        if "nilike" in self.model_fields_set:
            expressions.append(model_attribute.not_ilike(self.nilike))

        return expressions

    def _regexp_expressions(
        self, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if "regexp" in self.model_fields_set:
            expressions.append(model_attribute.regexp_match(self.regexp))
        if "nregexp" in self.model_fields_set:
            expressions.append(not_(model_attribute.regexp_match(self.nregexp)))
        if "iregexp" in self.model_fields_set:
            expressions.append(func.lower(model_attribute).regexp_match(self.iregexp))
        if "inregexp" in self.model_fields_set:
            expressions.append(not_(func.lower(model_attribute).regexp_match(self.inregexp)))

        return expressions

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
        expressions.extend(self._like_expressions(model_attribute))
        expressions.extend(self._regexp_expressions(model_attribute))

        if "startswith" in self.model_fields_set:
            expressions.append(model_attribute.startswith(self.startswith, autoescape=True))
        if "endswith" in self.model_fields_set:
            expressions.append(model_attribute.endswith(self.endswith, autoescape=True))
        if "contains" in self.model_fields_set:
            expressions.append(model_attribute.contains(self.contains, autoescape=True))
        if "istartswith" in self.model_fields_set:
            expressions.append(model_attribute.istartswith(self.istartswith, autoescape=True))
        if "iendswith" in self.model_fields_set:
            expressions.append(model_attribute.iendswith(self.iendswith, autoescape=True))
        if "icontains" in self.model_fields_set:
            expressions.append(model_attribute.icontains(self.icontains, autoescape=True))

        return expressions


class BaseDateSQLAlchemyFilter(DateComparison[OrderSQLAlchemyFilter[int], DeclarativeBase, QueryableAttribute[Any]]):
    """Base Date SQLAlchemy filter for date comparison operations.

    This class extends DateComparison and adds filtering
    capabilities for year, month, day, week, week_day, quarter,
    iso_week_day, and iso_year operations.
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
        expressions = super().to_expressions(dialect, model_attribute)
        if dialect.name == "postgresql":
            if "year" in self.model_fields_set and self.year:
                expressions.extend(self.year.to_expressions(dialect, func.extract("YEAR", model_attribute)))
            if "month" in self.model_fields_set and self.month:
                expressions.extend(self.month.to_expressions(dialect, func.extract("MONTH", model_attribute)))
            if "day" in self.model_fields_set and self.day:
                expressions.extend(self.day.to_expressions(dialect, func.extract("DAY", model_attribute)))
            if "week" in self.model_fields_set and self.week:
                expressions.extend(self.week.to_expressions(dialect, func.extract("WEEK", model_attribute)))
            if "week_day" in self.model_fields_set and self.week_day:
                expressions.extend(self.week_day.to_expressions(dialect, func.extract("DOW", model_attribute)))
            if "quarter" in self.model_fields_set and self.quarter:
                expressions.extend(self.quarter.to_expressions(dialect, func.extract("QUARTER", model_attribute)))
            if "iso_week_day" in self.model_fields_set and self.iso_week_day:
                expressions.extend(self.iso_week_day.to_expressions(dialect, func.extract("ISODOW", model_attribute)))
            if "iso_year" in self.model_fields_set and self.iso_year:
                expressions.extend(self.iso_year.to_expressions(dialect, func.extract("ISOYEAR", model_attribute)))

        return expressions


class BaseTimeSQLAlchemyFilter(TimeComparison[OrderSQLAlchemyFilter[int], DeclarativeBase, QueryableAttribute[Any]]):
    """Base Time SQLAlchemy filter for time comparison operations.

    This class extends TimeComparison and adds filtering
    capabilities for hour, minute, and second operations.
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
        expressions = super().to_expressions(dialect, model_attribute)

        if dialect.name == "postgresql":
            if "hour" in self.model_fields_set and self.hour:
                expressions.extend(self.hour.to_expressions(dialect, func.extract("HOUR", model_attribute)))
            if "minute" in self.model_fields_set and self.minute:
                expressions.extend(self.minute.to_expressions(dialect, func.extract("MINUTE", model_attribute)))
            if "second" in self.model_fields_set and self.second:
                expressions.extend(self.second.to_expressions(dialect, func.extract("SECOND", model_attribute)))

        return expressions


class DateSQLAlchemyFilter(BaseDateSQLAlchemyFilter, OrderSQLAlchemyFilter[date]):
    """Date SQLAlchemy filter for date comparison operations."""


class TimeSQLAlchemyFilter(BaseTimeSQLAlchemyFilter, OrderSQLAlchemyFilter[time]):
    """Time SQLAlchemy filter for time comparison operations."""


class TimeDeltaSQLAlchemyFilter(
    TimeDeltaComparison[OrderSQLAlchemyFilter[float], DeclarativeBase, QueryableAttribute[Any]],
    OrderSQLAlchemyFilter[timedelta],
):
    """Time delta SQLAlchemy filter for interval comparison operations."""

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[Any] | QueryableAttribute[Any]
    ) -> list[ColumnElement[bool]]:
        expressions = super().to_expressions(dialect, model_attribute)

        if dialect.name == "postgresql":
            if "days" in self.model_fields_set and self.days:
                seconds_in_day = 60 * 60 * 24
                expressions.extend(
                    self.days.to_expressions(dialect, func.extract("EPOCH", model_attribute) / seconds_in_day)
                )
            if "hours" in self.model_fields_set and self.hours:
                expressions.extend(self.hours.to_expressions(dialect, func.extract("EPOCH", model_attribute) / 3600))
            if "minutes" in self.model_fields_set and self.minutes:
                expressions.extend(self.minutes.to_expressions(dialect, func.extract("EPOCH", model_attribute) / 60))
            if "seconds" in self.model_fields_set and self.seconds:
                expressions.extend(self.seconds.to_expressions(dialect, func.extract("EPOCH", model_attribute)))

        return expressions


class DateTimeSQLAlchemyFilter(BaseDateSQLAlchemyFilter, BaseTimeSQLAlchemyFilter, OrderSQLAlchemyFilter[datetime]):
    """DateTime SQLAlchemy filter for datetime comparison operations."""

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
        return super().to_expressions(dialect, model_attribute)

    @override
    @classmethod
    def compared_type_name(cls) -> str:
        """Return the DTO field name.

        Returns:
            The DTO field name.
        """
        return "DateTime"
