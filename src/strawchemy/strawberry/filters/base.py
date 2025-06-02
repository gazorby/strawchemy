from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast, override

from sqlalchemy import ARRAY, JSON, ColumnElement, Dialect, Integer, Text, and_, func, not_, null, or_, type_coerce
from sqlalchemy import cast as sqla_cast
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects import postgresql as pg
from strawberry import UNSET

if TYPE_CHECKING:
    from datetime import date, timedelta

    from sqlalchemy.orm import QueryableAttribute

    from .inputs import (
        ArrayComparison,
        DateComparison,
        DateTimeComparison,
        EqualityComparison,
        GraphQLComparison,
        JSONComparison,
        OrderComparison,
        TextComparison,
        TimeComparison,
        TimeDeltaComparison,
    )


@dataclass(frozen=True)
class FilterProtocol(Protocol):
    comparison: GraphQLComparison

    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        return []


@dataclass(frozen=True)
class EqualityFilter(FilterProtocol):
    comparison: EqualityComparison[Any]

    @override
    def to_expressions(
        self,
        dialect: Dialect,
        model_attribute: QueryableAttribute[Any] | ColumnElement[Any],
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.eq is not UNSET:
            expressions.append(model_attribute == self.comparison.eq)
        if self.comparison.neq is not UNSET:
            expressions.append(model_attribute != self.comparison.neq)
        if self.comparison.in_ is not UNSET and self.comparison.in_:
            expressions.append(model_attribute.in_(self.comparison.in_))
        if self.comparison.nin is not UNSET and self.comparison.nin:
            expressions.append(model_attribute.not_in(self.comparison.nin))
        if self.comparison.is_null is not UNSET:
            expressions.append(
                model_attribute.is_(null()) if self.comparison.is_null else model_attribute.is_not(null())
            )

        return expressions


@dataclass(frozen=True)
class OrderFilter(EqualityFilter):
    comparison: OrderComparison[Any]

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[Any] | ColumnElement[Any]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)

        if self.comparison.gt is not UNSET:
            expressions.append(model_attribute > self.comparison.gt)
        if self.comparison.gte is not UNSET:
            expressions.append(model_attribute >= self.comparison.gte)
        if self.comparison.lt is not UNSET:
            expressions.append(model_attribute < self.comparison.lt)
        if self.comparison.lte is not UNSET:
            expressions.append(model_attribute <= self.comparison.lte)

        return expressions


@dataclass(frozen=True)
class TextFilter(OrderFilter):
    comparison: TextComparison

    def _like_expressions(
        self, model_attribute: QueryableAttribute[str] | ColumnElement[str]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.like is not UNSET:
            expressions.append(model_attribute.like(self.comparison.like))
        if self.comparison.nlike is not UNSET:
            expressions.append(model_attribute.not_like(self.comparison.nlike))
        if self.comparison.ilike is not UNSET:
            expressions.append(model_attribute.ilike(self.comparison.ilike))
        if self.comparison.nilike is not UNSET:
            expressions.append(model_attribute.not_ilike(self.comparison.nilike))

        return expressions

    def _regexp_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[str] | ColumnElement[str]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []
        if self.comparison.regexp is not UNSET or self.comparison.nregexp is not UNSET:
            regex = self.comparison.regexp or self.comparison.nregexp
            if dialect.name == "mysql":
                regex_comp = func.regexp_like(model_attribute, regex, "c")
            else:
                regex_comp = model_attribute.regexp_match(regex)
            if self.comparison.regexp is not UNSET:
                expressions.append(regex_comp)
            else:
                expressions.append(not_(regex_comp))
        if self.comparison.iregexp is not UNSET:
            expressions.append(func.lower(model_attribute).regexp_match(self.comparison.iregexp))
        if self.comparison.inregexp is not UNSET:
            expressions.append(not_(func.lower(model_attribute).regexp_match(self.comparison.inregexp)))

        return expressions

    @override
    def to_expressions(
        self,
        dialect: Dialect,
        model_attribute: QueryableAttribute[str] | ColumnElement[str],
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)
        expressions.extend(self._like_expressions(model_attribute))
        expressions.extend(self._regexp_expressions(dialect, model_attribute))

        if self.comparison.startswith is not UNSET:
            expressions.append(model_attribute.startswith(self.comparison.startswith, autoescape=True))
        if self.comparison.endswith is not UNSET:
            expressions.append(model_attribute.endswith(self.comparison.endswith, autoescape=True))
        if self.comparison.contains is not UNSET:
            expressions.append(model_attribute.contains(self.comparison.contains, autoescape=True))
        if self.comparison.istartswith is not UNSET:
            expressions.append(model_attribute.istartswith(self.comparison.istartswith, autoescape=True))
        if self.comparison.iendswith is not UNSET:
            expressions.append(model_attribute.iendswith(self.comparison.iendswith, autoescape=True))
        if self.comparison.icontains is not UNSET:
            expressions.append(model_attribute.icontains(self.comparison.icontains, autoescape=True))

        return expressions


@dataclass(frozen=True)
class JSONFilter(EqualityFilter):
    comparison: JSONComparison

    def _postgres_json(
        self, model_attribute: ColumnElement[JSON] | QueryableAttribute[JSON]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []
        as_postgres_jsonb = type_coerce(model_attribute, pg.JSONB)

        if self.comparison.contains is not UNSET:
            expressions.append(as_postgres_jsonb.contains(self.comparison.contains))
        if self.comparison.contained_in is not UNSET:
            expressions.append(as_postgres_jsonb.contained_by(self.comparison.contained_in))
        if self.comparison.has_key is not UNSET:
            expressions.append(as_postgres_jsonb.has_key(self.comparison.has_key))
        if self.comparison.has_key_all is not UNSET:
            expressions.append(as_postgres_jsonb.has_all(sqla_cast(self.comparison.has_key_all, pg.ARRAY(Text))))
        if self.comparison.has_key_any is not UNSET:
            expressions.append(as_postgres_jsonb.has_any(sqla_cast(self.comparison.has_key_any, pg.ARRAY(Text))))
        return expressions

    def _mysql_json(self, model_attribute: ColumnElement[JSON] | QueryableAttribute[JSON]) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []
        as_mysql_json = type_coerce(model_attribute, mysql.JSON)

        if self.comparison.contains is not UNSET:
            expressions.append(func.json_contains(as_mysql_json, sqla_cast(self.comparison.contains, mysql.JSON)))
        if self.comparison.contained_in is not UNSET:
            expressions.append(func.json_contains(sqla_cast(self.comparison.contained_in, mysql.JSON), as_mysql_json))
        if self.comparison.has_key is not UNSET:
            expressions.append(func.json_contains_path(as_mysql_json, "all", f"$.{self.comparison.has_key}"))
        if self.comparison.has_key_all is not UNSET and self.comparison.has_key_all:
            expressions.append(
                func.json_contains_path(as_mysql_json, "all", *[f"$.{key}" for key in self.comparison.has_key_all])
            )
        if self.comparison.has_key_any is not UNSET and self.comparison.has_key_any:
            expressions.append(
                func.json_contains_path(as_mysql_json, "one", *[f"$.{key}" for key in self.comparison.has_key_any])
            )
        return expressions

    def _sqlite_json(
        self, model_attribute: ColumnElement[JSON] | QueryableAttribute[JSON]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.has_key is not UNSET:
            expressions.append(func.json_extract(model_attribute, f"$.{self.comparison.has_key}").is_not(null()))
        if self.comparison.has_key_all is not UNSET and self.comparison.has_key_all:
            expressions.append(
                and_(
                    *[
                        func.json_extract(model_attribute, f"$.{key}").is_not(null())
                        for key in self.comparison.has_key_all
                    ]
                )
            )
        if self.comparison.has_key_any is not UNSET and self.comparison.has_key_any:
            expressions.append(
                or_(
                    *[
                        func.json_extract(model_attribute, f"$.{key}").is_not(null())
                        for key in self.comparison.has_key_any
                    ]
                )
            )
        return expressions

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: QueryableAttribute[JSON] | ColumnElement[JSON]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)

        if dialect.name == "postgresql":
            expressions.extend(self._postgres_json(model_attribute))
        elif dialect.name == "mysql":
            expressions.extend(self._mysql_json(model_attribute))
        elif dialect.name == "sqlite":
            expressions.extend(self._sqlite_json(model_attribute))

        return expressions


@dataclass(frozen=True)
class ArrayFilter(EqualityFilter):
    comparison: ArrayComparison[Any]

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[ARRAY[Any]] | QueryableAttribute[ARRAY[Any]]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = super().to_expressions(dialect, model_attribute)
        as_postgres_array = type_coerce(model_attribute, pg.ARRAY(cast("ARRAY[Any]", model_attribute.type).item_type))

        if self.comparison.contains is not UNSET:
            expressions.append(as_postgres_array.contains(self.comparison.contains))
        if self.comparison.contained_in is not UNSET:
            expressions.append(as_postgres_array.contained_by(self.comparison.contained_in))
        if self.comparison.overlap is not UNSET:
            expressions.append(as_postgres_array.overlap(self.comparison.overlap))
        return expressions


@dataclass(frozen=True)
class BaseDateFilter(FilterProtocol):
    comparison: DateComparison | DateTimeComparison

    def _sqlite_date(
        self, dialect: Dialect, model_attribute: ColumnElement[date] | QueryableAttribute[date]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.year is not UNSET and self.comparison.year:
            expressions.extend(
                self.comparison.year.to_expressions(dialect, sqla_cast(func.strftime("%Y", model_attribute), Integer))
            )
        if self.comparison.month is not UNSET and self.comparison.month:
            expressions.extend(
                self.comparison.month.to_expressions(dialect, sqla_cast(func.strftime("%m", model_attribute), Integer))
            )
        if self.comparison.day is not UNSET and self.comparison.day:
            expressions.extend(
                self.comparison.day.to_expressions(dialect, sqla_cast(func.strftime("%e", model_attribute), Integer))
            )
        if self.comparison.week is not UNSET and self.comparison.week:
            expressions.extend(
                self.comparison.week.to_expressions(dialect, sqla_cast(func.strftime("%V", model_attribute), Integer))
            )
        if self.comparison.week_day is not UNSET and self.comparison.week_day:
            expressions.extend(
                self.comparison.week_day.to_expressions(
                    dialect, sqla_cast(func.strftime("%w", model_attribute), Integer)
                )
            )
        if self.comparison.quarter is not UNSET and self.comparison.quarter:
            expressions.extend(
                self.comparison.quarter.to_expressions(
                    dialect,
                    sqla_cast((sqla_cast(func.strftime("%m", model_attribute), Integer) + 2) / 3, Integer),
                )
            )
        if self.comparison.iso_week_day is not UNSET and self.comparison.iso_week_day:
            expressions.extend(
                self.comparison.iso_week_day.to_expressions(
                    dialect, sqla_cast(func.strftime("%u", model_attribute), Integer)
                )
            )
        if self.comparison.iso_year is not UNSET and self.comparison.iso_year:
            expressions.extend(
                self.comparison.iso_year.to_expressions(
                    dialect, sqla_cast(func.strftime("%G", model_attribute), Integer)
                )
            )

        return expressions

    def _postgres_date(
        self, dialect: Dialect, model_attribute: ColumnElement[date] | QueryableAttribute[date]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.year is not UNSET and self.comparison.year:
            expressions.extend(self.comparison.year.to_expressions(dialect, func.extract("YEAR", model_attribute)))
        if self.comparison.month is not UNSET and self.comparison.month:
            expressions.extend(self.comparison.month.to_expressions(dialect, func.extract("MONTH", model_attribute)))
        if self.comparison.day is not UNSET and self.comparison.day:
            expressions.extend(self.comparison.day.to_expressions(dialect, func.extract("DAY", model_attribute)))
        if self.comparison.week is not UNSET and self.comparison.week:
            expressions.extend(self.comparison.week.to_expressions(dialect, func.extract("WEEK", model_attribute)))
        if self.comparison.week_day is not UNSET and self.comparison.week_day:
            expressions.extend(self.comparison.week_day.to_expressions(dialect, func.extract("DOW", model_attribute)))
        if self.comparison.quarter is not UNSET and self.comparison.quarter:
            expressions.extend(
                self.comparison.quarter.to_expressions(dialect, func.extract("QUARTER", model_attribute))
            )
        if self.comparison.iso_week_day is not UNSET and self.comparison.iso_week_day:
            expressions.extend(
                self.comparison.iso_week_day.to_expressions(dialect, func.extract("ISODOW", model_attribute))
            )
        if self.comparison.iso_year is not UNSET and self.comparison.iso_year:
            expressions.extend(
                self.comparison.iso_year.to_expressions(dialect, func.extract("ISOYEAR", model_attribute))
            )

        return expressions

    def _mysql_date(
        self, dialect: Dialect, model_attribute: ColumnElement[date] | QueryableAttribute[date]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.year is not UNSET and self.comparison.year:
            expressions.extend(self.comparison.year.to_expressions(dialect, func.extract("YEAR", model_attribute)))
        if self.comparison.month is not UNSET and self.comparison.month:
            expressions.extend(self.comparison.month.to_expressions(dialect, func.extract("MONTH", model_attribute)))
        if self.comparison.day is not UNSET and self.comparison.day:
            expressions.extend(self.comparison.day.to_expressions(dialect, func.extract("DAY", model_attribute)))
        if self.comparison.week is not UNSET and self.comparison.week:
            expressions.extend(self.comparison.week.to_expressions(dialect, func.week(model_attribute, 3)))
        if self.comparison.week_day is not UNSET and self.comparison.week_day:
            expressions.extend(
                self.comparison.week_day.to_expressions(dialect, func.date_format(model_attribute, "%w"))
            )
        if self.comparison.quarter is not UNSET and self.comparison.quarter:
            expressions.extend(
                self.comparison.quarter.to_expressions(dialect, func.extract("QUARTER", model_attribute))
            )
        if self.comparison.iso_week_day is not UNSET and self.comparison.iso_week_day:
            expressions.extend(self.comparison.iso_week_day.to_expressions(dialect, func.weekday(model_attribute) + 1))
        if self.comparison.iso_year is not UNSET and self.comparison.iso_year:
            expressions.extend(
                self.comparison.iso_year.to_expressions(dialect, func.date_format(model_attribute, "%x"))
            )

        return expressions

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[Any] | QueryableAttribute[Any]
    ) -> list[ColumnElement[bool]]:
        expressions = super().to_expressions(dialect, model_attribute)
        if dialect.name == "postgresql":
            expressions.extend(self._postgres_date(dialect, model_attribute))
        elif dialect.name == "mysql":
            expressions.extend(self._mysql_date(dialect, model_attribute))
        elif dialect.name == "sqlite":
            expressions.extend(self._sqlite_date(dialect, model_attribute))

        return expressions


@dataclass(frozen=True)
class BaseTimeFilter(FilterProtocol):
    comparison: TimeComparison | DateTimeComparison

    def _sqlite_time(
        self, dialect: Dialect, model_attribute: ColumnElement[date] | QueryableAttribute[date]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.hour:
            expressions.extend(
                self.comparison.hour.to_expressions(dialect, sqla_cast(func.strftime("%H", model_attribute), Integer))
            )
        if self.comparison.minute:
            expressions.extend(
                self.comparison.minute.to_expressions(dialect, sqla_cast(func.strftime("%M", model_attribute), Integer))
            )
        if self.comparison.second:
            expressions.extend(
                self.comparison.second.to_expressions(dialect, sqla_cast(func.strftime("%S", model_attribute), Integer))
            )

        return expressions

    def _extract_time(
        self, dialect: Dialect, model_attribute: ColumnElement[date] | QueryableAttribute[date]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.hour:
            expressions.extend(self.comparison.hour.to_expressions(dialect, func.extract("HOUR", model_attribute)))
        if self.comparison.minute:
            expressions.extend(self.comparison.minute.to_expressions(dialect, func.extract("MINUTE", model_attribute)))
        if self.comparison.second:
            expressions.extend(self.comparison.second.to_expressions(dialect, func.extract("SECOND", model_attribute)))

        return expressions

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[Any] | QueryableAttribute[Any]
    ) -> list[ColumnElement[bool]]:
        expressions = super().to_expressions(dialect, model_attribute)

        if dialect.name == "sqlite":
            expressions.extend(self._sqlite_time(dialect, model_attribute))
        else:
            expressions.extend(self._extract_time(dialect, model_attribute))

        return expressions


@dataclass(frozen=True)
class TimeDeltaFilter(OrderFilter):
    comparison: TimeDeltaComparison
    _seconds_in_day: ClassVar[int] = 60 * 60 * 24

    def _postgres_interval(
        self, dialect: Dialect, model_attribute: ColumnElement[timedelta] | QueryableAttribute[timedelta]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.days:
            expressions.extend(
                self.comparison.days.to_expressions(
                    dialect, func.extract("EPOCH", model_attribute) / self._seconds_in_day
                )
            )
        if self.comparison.hours:
            expressions.extend(
                self.comparison.hours.to_expressions(dialect, func.extract("EPOCH", model_attribute) / 3600)
            )
        if self.comparison.minutes:
            expressions.extend(
                self.comparison.minutes.to_expressions(dialect, func.extract("EPOCH", model_attribute) / 60)
            )
        if self.comparison.seconds:
            expressions.extend(self.comparison.seconds.to_expressions(dialect, func.extract("EPOCH", model_attribute)))

        return expressions

    def _mysql_interval(
        self, dialect: Dialect, model_attribute: ColumnElement[timedelta] | QueryableAttribute[timedelta]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.days:
            expressions.extend(
                self.comparison.days.to_expressions(
                    dialect, func.unix_timestamp(model_attribute) / self._seconds_in_day
                )
            )
        if self.comparison.hours:
            expressions.extend(
                self.comparison.hours.to_expressions(dialect, func.unix_timestamp(model_attribute) / 3600)
            )
        if self.comparison.minutes:
            expressions.extend(
                self.comparison.minutes.to_expressions(dialect, func.unix_timestamp(model_attribute) / 60)
            )
        if self.comparison.seconds:
            expressions.extend(self.comparison.seconds.to_expressions(dialect, func.unix_timestamp(model_attribute)))

        return expressions

    def _sqlite_interval(
        self, dialect: Dialect, model_attribute: ColumnElement[timedelta] | QueryableAttribute[timedelta]
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []

        if self.comparison.days:
            expressions.extend(
                self.comparison.days.to_expressions(
                    dialect, sqla_cast(func.strftime("%s", model_attribute), Integer) / self._seconds_in_day
                )
            )
        if self.comparison.hours:
            expressions.extend(
                self.comparison.hours.to_expressions(
                    dialect, sqla_cast(func.strftime("%s", model_attribute), Integer) / 3600
                )
            )
        if self.comparison.minutes:
            expressions.extend(
                self.comparison.minutes.to_expressions(
                    dialect, sqla_cast(func.strftime("%s", model_attribute), Integer) / 60
                )
            )
        if self.comparison.seconds:
            expressions.extend(
                self.comparison.seconds.to_expressions(
                    dialect, sqla_cast(func.strftime("%s", model_attribute), Integer)
                )
            )

        return expressions

    @override
    def to_expressions(
        self, dialect: Dialect, model_attribute: ColumnElement[timedelta] | QueryableAttribute[timedelta]
    ) -> list[ColumnElement[bool]]:
        expressions = super().to_expressions(dialect, model_attribute)

        if dialect.name == "postgresql":
            expressions.extend(self._postgres_interval(dialect, model_attribute))
        elif dialect.name == "mysql":
            expressions.extend(self._mysql_interval(dialect, model_attribute))
        elif dialect.name == "sqlite":
            expressions.extend(self._sqlite_interval(dialect, model_attribute))

        return expressions


@dataclass(frozen=True)
class DateFilter(BaseDateFilter, OrderFilter):
    comparison: DateComparison


@dataclass(frozen=True)
class TimeFilter(BaseTimeFilter, OrderFilter):
    comparison: TimeComparison


@dataclass(frozen=True)
class DateTimeFilter(BaseDateFilter, BaseTimeFilter, OrderFilter):
    comparison: DateTimeComparison
