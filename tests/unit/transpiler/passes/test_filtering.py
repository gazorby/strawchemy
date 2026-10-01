"""Tests for the ``Filtering`` pass: WHERE predicates, the joins they need and the EXISTS they test."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from strawberry.types import get_object_definition

from strawchemy import Strawchemy
from strawchemy.transpiler import Transpiler
from tests.duplicate_reads import assert_no_duplicate_reads
from tests.unit.models import Color, Department, Fruit, Group, Tag, User, UUIDBase
from tests.unit.schemas.optimizations import ColorFilter, schema
from tests.unit.transpiler.passes.utils import plan_sql
from tests.unit.utils import SQLA_DIALECTS
from tests.utils import format_sql

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Select

    from strawchemy.dto.strawberry import AggregateFilterDTO, BooleanFilterDTO

_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
_SEEDED_TABLES = ("color", "fruit", "tag", "group", "user", "department", "user_department_join_table")
_USERS_NOT_TAGGED_IN_UNNAMED_DEPARTMENT = (
    '{ groups(filter: { users: { _not: { tag: { name: { eq: "x" } }, departments: { name: { isNull: true } } } } }) '
    "{ name } }"
)


class _PairBase(DeclarativeBase):
    pass


class _Pair(_PairBase):
    __tablename__ = "pair"

    left_id: Mapped[int] = mapped_column(primary_key=True)
    right_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


def _named_pair(statement: Select[tuple[_Pair]], value: str, **_ctx: object) -> Select[tuple[_Pair]]:
    return statement.where(_Pair.name == value)


_strawchemy = Strawchemy("postgresql")


@_strawchemy.filter(_Pair, include=["name"])
class _PairCustomFilter:
    named_in: str = _strawchemy.filter_field(apply=_named_pair, join="in")


@dataclass(frozen=True)
class _SessionContext:
    session: Session


def _where(lines: list[str]) -> list[str]:
    start = next(index for index, line in enumerate(lines) if line.startswith(" WHERE"))
    end = next((index for index, line in enumerate(lines) if line.startswith(" ORDER BY")), len(lines))
    return [line.strip() for line in lines[start:end]]


def _input_type(dto: type[Any], name: str) -> type[Any]:
    field = next(field for field in get_object_definition(dto, strict=True).fields if field.python_name == name)
    return cast("type[Any]", getattr(field.type, "of_type", field.type))


def _queried_names(session: Session, query: str, field: str) -> set[str]:
    """Runs ``query`` on ``session`` and returns the names of the rows of its ``field``."""
    result = schema.execute_sync(query, context_value=_SessionContext(session))
    assert not result.errors, result.errors
    assert result.data is not None
    return {row["name"] for row in result.data[field]}


def _fruit_named(name: str) -> BooleanFilterDTO:
    fruit_filter = _input_type(ColorFilter, "fruits")
    return fruit_filter(name=_input_type(fruit_filter, "name")(eq=name))


def _more_fruits_than(count: int) -> AggregateFilterDTO:
    aggregation_filter = _input_type(ColorFilter, "fruits_aggregate")
    count_filter = _input_type(aggregation_filter, "count")
    return aggregation_filter(count=count_filter(predicate=_input_type(count_filter, "predicate")(gt=count)))


def _updated_colors(session: Session, dto_filter: BooleanFilterDTO) -> set[str]:
    """Seeds colors named after their fruits, updates those ``dto_filter`` matches on SQLite and returns their names."""
    fruit_names = {"two": ["x", "z"], "three": ["x", "z", "w"], "no_z": ["x", "w", "v"], "no_x": ["z", "w", "v"]}
    session.add_all(
        Color(name=name, private="", fruits=[Fruit(name=fruit, sweetness=0, private="") for fruit in fruits])
        for name, fruits in {**fruit_names, "empty": []}.items()
    )
    session.flush()
    expressions = Transpiler(Color, SQLA_DIALECTS["sqlite"]).filter_expressions(dto_filter)
    session.execute(update(Color).where(*expressions).values(private="updated"))
    return set(session.scalars(select(Color.name).where(Color.private == "updated")))


@pytest.fixture
def sqlite_session() -> Iterator[Session]:
    """Yields a session on an in-memory SQLite database holding the tables the seeded tests write."""
    engine = create_engine("sqlite://")
    UUIDBase.metadata.create_all(engine, tables=[UUIDBase.metadata.tables[name] for name in _SEEDED_TABLES])
    with Session(engine) as session:
        yield session
    engine.dispose()


@_DIALECTS
def test_to_one_filter_inner_join(dialect_name: str) -> None:
    """A to-one filter inner-joins its relation once, and the selection of that relation reads the same join."""
    lines = plan_sql('{ groups(filter: { color: { name: { eq: "x" } } }) { color { name } } }', dialect_name)

    inner_join = "INNER JOIN color AS color_1" if dialect_name == "mysql" else "JOIN color AS color_1"
    assert [line.strip() for line in lines if "JOIN" in line] == [inner_join]
    assert _where(lines)[0].startswith("WHERE color_1.name = ")
    assert "       color_1.name," in lines


@_DIALECTS
def test_to_many_filter_exists_without_root_copy(dialect_name: str) -> None:
    """A to-many filter is an EXISTS on the related table correlated to the root, without a copy of the root."""
    lines = plan_sql("{ colors(filter: { fruits: { sweetness: { gt: 1 } } }) { fruits { sweetness } } }", dialect_name)

    where = _where(lines)
    assert where[:3] == ["WHERE EXISTS (", "SELECT 1", "FROM fruit AS fruit_2"]
    assert not any(line.startswith(("FROM color", "JOIN color", "INNER JOIN color")) for line in where)
    assert "color.id = fruit_2.color_id" in " ".join(where)


def _true(dialect_name: str) -> str:
    return "1" if dialect_name == "sqlite" else "TRUE"


def _reads_in_exists(where: str, table: str) -> int:
    """Counts the FROM and JOIN entries reading ``table`` inside the EXISTS subqueries of ``where``."""
    return len(re.findall(rf"(?:FROM|JOIN) {table} AS", where))


@_DIALECTS
def test_or_of_to_many_and_root_predicate_splits_exists(dialect_name: str) -> None:
    """A to-many branch OR-ed with a root predicate is an EXISTS on the relation OR the predicate, without root copy."""
    lines = plan_sql(
        '{ colors(filter: { _or: [{ fruits: { sweetness: { gt: 5 } } }, { name: { eq: "red" } }] }) { name } }',
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert "EXISTS (SELECT 1 FROM fruit AS fruit_1" in where
    assert "OR color.name = " in where
    assert _reads_in_exists(where, "color") == 0
    assert "OUTER JOIN" not in where


@_DIALECTS
def test_or_across_two_relations_is_two_exists(dialect_name: str) -> None:
    """An OR across two relations is one EXISTS per relation, joined by OR, without root copy or outer join."""
    lines = plan_sql(
        '{ groups(filter: { _or: [{ users: { name: { eq: "x" } } }, { color: { fruits: { name: { eq: "y" } } } }] }) '
        "{ name } }",
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert where.count("EXISTS (") == 2
    assert ") OR (EXISTS (" in where
    assert _reads_in_exists(where, '"group"' if dialect_name != "mysql" else "`group`") == 0
    assert "OUTER JOIN" not in where


@_DIALECTS
def test_not_of_or_distributes(dialect_name: str) -> None:
    """A NOT over an OR of a to-many branch and a root predicate tests their EXISTS OR predicate is not true."""
    lines = plan_sql(
        '{ colors(filter: { _not: { _or: [{ fruits: { sweetness: { gt: 5 } } }, { name: { eq: "red" } }] } }) '
        "{ name } }",
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert where.startswith("WHERE ((EXISTS (SELECT 1 FROM fruit AS fruit_1")
    assert ") OR color.name = " in where
    assert where.endswith(f") IS NOT {_true(dialect_name)}")
    assert _reads_in_exists(where, "color") == 0


@_DIALECTS
def test_not_of_or_under_to_one_distributes(dialect_name: str) -> None:
    """Under a to-one relation, a NOT over an OR of a to-many branch and a column is tested on the joined relation."""
    lines = plan_sql(
        "{ groups(filter: { color: { _not: { _or: [{ fruits: { sweetness: { gt: 5 } } }, "
        '{ name: { eq: "red" } }] } } }) { name } }',
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert "WHERE ((EXISTS (SELECT 1 FROM fruit AS fruit_1 WHERE color_1.id = fruit_1.color_id" in where
    assert ") OR color_1.name = " in where
    assert where.endswith(f") IS NOT {_true(dialect_name)}")
    assert _reads_in_exists(where, "color") == 0


@_DIALECTS
def test_not_of_or_with_aggregate_under_to_one_reads_no_copy(dialect_name: str) -> None:
    """Under a to-one relation, a NOT over an OR of an aggregate and a to-many branch is tested on the joined relation."""
    lines = plan_sql(
        "{ groups(filter: { color: { _not: { _or: [{ fruitsAggregate: { count: { predicate: { gt: 2 } } } }, "
        '{ fruits: { name: { eq: "kiwi" } } }] } } }) { name } }',
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert "EXISTS (SELECT 1 FROM fruit AS fruit_2 WHERE color_1.id = fruit_2.color_id" in where
    assert where.endswith(f") IS NOT {_true(dialect_name)}")
    assert _reads_in_exists(where, "color") == 0


@_DIALECTS
def test_not_of_or_with_aggregate_under_to_many_reads_no_copy(dialect_name: str) -> None:
    """Under a to-many relation, a NOT over an OR of an aggregate and a to-many branch reads the relation once."""
    lines = plan_sql(
        "{ groups(filter: { users: { _not: { _or: [{ departmentsAggregate: { count: { predicate: { gt: 0 } } } }, "
        '{ departments: { name: { eq: "d" } } }] } } }) { name } }',
        dialect_name,
    )

    sql = " ".join(line.strip() for line in lines)
    user_table = '"user"' if dialect_name == "postgresql" else "USER"
    assert sql.count(f"FROM {user_table} AS") == 1 + (dialect_name != "postgresql")
    assert f") IS NOT {_true(dialect_name)}" in sql


@_DIALECTS
def test_and_inside_or_branch_keeps_one_exists(dialect_name: str) -> None:
    """Two predicates ANDed on one to-many relation in an OR branch stay in one EXISTS, so one row passes both."""
    lines = plan_sql(
        '{ colors(filter: { _or: [{ fruits: { sweetness: { gt: 5 }, name: { eq: "apple" } } }, '
        '{ name: { eq: "red" } }] }) { name } }',
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert where.count("EXISTS (") == 1
    exists_body = where[where.index("EXISTS (") : where.index(") OR color.name = ")]
    assert "fruit_1.name = " in exists_body
    assert "fruit_1.sweetness > " in exists_body
    assert _reads_in_exists(where, "color") == 0


@_DIALECTS
def test_not_adds_null_check(dialect_name: str) -> None:
    """Under NOT, a comparison also requires its column to be non-null, so that a NULL fails it."""
    lines = plan_sql('{ colors(filter: { _not: { name: { eq: "x" } } }) { name } }', dialect_name)

    where = " ".join(_where(lines))
    assert where.startswith("WHERE NOT (color.name = ")
    assert where.endswith("AND color.name IS NOT NULL)")


@_DIALECTS
def test_and_branch_aggregating_a_shared_to_many_is_tested_on_the_relation_rows(dialect_name: str) -> None:
    """Under a to-one, an ``_and`` branch aggregating a to-many the fields also join is tested on the joined rows."""
    lines = plan_sql(
        '{ groups(filter: { color: { fruits: { name: { eq: "x" } }, _and: [{ fruitsAggregate: { count: { predicate: '
        '{ gt: 1 } } }, fruits: { name: { eq: "z" } } }] } }) { name } }',
        dialect_name,
    )

    where = " ".join(_where(lines))
    assert where.startswith("WHERE EXISTS ( SELECT 1 FROM color AS color_1")
    assert "(EXISTS (SELECT 1 FROM fruit AS fruit_3 WHERE color_1.id = fruit_3.color_id AND fruit_3.name = " in where
    assert "AND fruit_2.name = " in where
    assert _reads_in_exists(where, "color") == 1


@_DIALECTS
def test_or_on_outer_relation_guards_missing_row(dialect_name: str) -> None:
    """A to-one relation tested under one OR branch only is outer-joined, and its branch requires a related row."""
    lines = plan_sql(
        '{ groups(filter: { _or: [{ color: { name: { eq: "x" } } }, { name: { eq: "y" } }] }) { name } }',
        dialect_name,
    )

    assert [line.strip() for line in lines if "JOIN" in line] == ["LEFT OUTER JOIN color AS color_1"]
    assert "color_1.id IS NOT NULL" in " ".join(_where(lines))


@_DIALECTS
def test_custom_filter_in_single_pk(dialect_name: str) -> None:
    """A custom filter joined with ``in`` matches the root's single primary key against the callback's keys."""
    lines = plan_sql('{ colorsCustomFilter(filter: { namedIn: "x" }) { name } }', dialect_name)

    assert " ".join(_where(lines)).startswith(
        "WHERE color.id IN ( SELECT custom_filter.id FROM color AS custom_filter WHERE custom_filter.name = "
    )


@_DIALECTS
def test_custom_filter_in_composite_pk(dialect_name: str) -> None:
    """A custom filter joined with ``in`` on a composite primary key matches the key tuple against the callback's."""
    dialect = SQLA_DIALECTS[dialect_name]

    expressions = Transpiler(_Pair, dialect).filter_expressions(_PairCustomFilter(named_in="x"))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    sql = " ".join(format_sql(str(update(_Pair).values(name="y").where(*expressions).compile(dialect=dialect))).split())
    assert "WHERE (pair.left_id, pair.right_id) IN ( SELECT custom_filter.left_id, custom_filter.right_id" in sql
    assert "FROM pair AS custom_filter WHERE custom_filter.name = " in sql


def test_aggregate_filter_shares_join() -> None:
    """A filtered and selected aggregation is computed by one LATERAL join."""
    lines = plan_sql(
        "{ colors(filter: { fruitsAggregate: { count: { predicate: { gt: 0 } } } }) { fruitsAggregate { count } } }",
        "postgresql",
    )

    assert sum("LATERAL" in line for line in lines) == 1
    assert any(line.strip().startswith("WHERE anon_1.count_1 > ") for line in lines)


def test_filter_expressions_mysql_derived_table() -> None:
    """On MySQL, a DML relation filter reads the matched keys through ``dml_matched``, correlated to the real table."""
    fruit_filter = _input_type(ColorFilter, "fruits")
    text_comparison = _input_type(fruit_filter, "name")
    dto_filter = ColorFilter(fruits=fruit_filter(name=text_comparison(eq="x")))  # ty: ignore[unknown-argument]  # input fields are generated at runtime
    dialect = SQLA_DIALECTS["mysql"]

    expressions = Transpiler(Color, dialect).filter_expressions(dto_filter)

    statement = select(Color.id).where(*expressions)
    assert_no_duplicate_reads(statement, dialect)
    sql = " ".join(line.strip() for line in format_sql(str(statement.compile(dialect=dialect))).splitlines())
    assert ") AS dml_matched" in sql
    assert "FROM color AS color_1 INNER JOIN fruit AS fruit_1" in sql
    assert sql.endswith("WHERE dml_matched.id = color.id )")


def _dml_sql(dto_filter: BooleanFilterDTO, dialect_name: str) -> str:
    dialect = SQLA_DIALECTS[dialect_name]
    statement = update(Color).values(name="y").where(*Transpiler(Color, dialect).filter_expressions(dto_filter))
    return " ".join(format_sql(str(statement.compile(dialect=dialect))).split())


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite"])
def test_filter_expressions_not_to_many_is_a_not_exists_on_the_table(dialect_name: str) -> None:
    """A DML ``_not`` over a to-many relation is a NOT EXISTS correlated to the table, without a copy of the root."""
    fruit_filter = _input_type(ColorFilter, "fruits")
    text_comparison = _input_type(fruit_filter, "name")
    dto_filter = ColorFilter(not_=ColorFilter(fruits=fruit_filter(name=text_comparison(eq="x"))))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    sql = _dml_sql(dto_filter, dialect_name)

    assert "WHERE NOT (EXISTS (SELECT 1 FROM fruit AS fruit_1 WHERE color.id = fruit_1.color_id" in sql
    assert "FROM color" not in sql


@pytest.mark.parametrize(
    ("negated", "updated"),
    [pytest.param(False, {"three"}, id="and"), pytest.param(True, {"two", "no_z", "no_x", "empty"}, id="not")],
)
def test_filter_expressions_and_branch_aggregating_a_shared_to_many(
    negated: bool, updated: set[str], sqlite_session: Session
) -> None:
    """A DML ``_and`` branch counting a to-many relation the fields also filter, or its ``_not``, updates the matches."""
    branch = ColorFilter(fruits_aggregate=_more_fruits_than(2), fruits=_fruit_named("z"))  # ty: ignore[unknown-argument]  # input fields are generated at runtime
    dto_filter = ColorFilter(fruits=_fruit_named("x"), and_=[branch])  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    names = _updated_colors(sqlite_session, ColorFilter(not_=dto_filter) if negated else dto_filter)  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    assert names == updated


def test_filter_expressions_not_of_not_aggregating_a_to_many(sqlite_session: Session) -> None:
    """A DML ``_not`` of a ``_not`` testing a to-many relation and counting it updates the colors passing both."""
    tested = ColorFilter(fruits=_fruit_named("x"), fruits_aggregate=_more_fruits_than(2))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    names = _updated_colors(sqlite_session, ColorFilter(not_=ColorFilter(not_=tested)))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    assert names == {"three", "no_z"}


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite"])
def test_filter_expressions_not_of_or_fails_null_column(dialect_name: str) -> None:
    """A DML NOT over an OR of a to-many branch and a column makes a NULL column fail the column predicate."""
    fruit_filter = _input_type(ColorFilter, "fruits")
    text_comparison = _input_type(fruit_filter, "name")
    fruit_branch = ColorFilter(fruits=fruit_filter(name=text_comparison(eq="x")))  # ty: ignore[unknown-argument]  # input fields are generated at runtime
    name_branch = ColorFilter(name=text_comparison(eq="y"))  # ty: ignore[unknown-argument]  # input fields are generated at runtime
    dto_filter = ColorFilter(not_=ColorFilter(or_=[fruit_branch, name_branch]))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    sql = _dml_sql(dto_filter, dialect_name)

    assert "WHERE NOT ((EXISTS (SELECT 1 FROM fruit AS fruit_1 WHERE color.id = fruit_1.color_id" in sql
    assert sql.endswith("AND color.name IS NOT NULL))")
    assert "FROM color" not in sql


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite"])
def test_filter_expressions_or_of_relation_and_column_splits_exists(dialect_name: str) -> None:
    """A DML OR of a to-many branch and a column is an EXISTS correlated to the table OR the column predicate."""
    fruit_filter = _input_type(ColorFilter, "fruits")
    text_comparison = _input_type(fruit_filter, "name")
    dto_filter = ColorFilter(
        or_=[ColorFilter(fruits=fruit_filter(name=text_comparison(eq="x"))), ColorFilter(name=text_comparison(eq="y"))]  # ty: ignore[unknown-argument]  # input fields are generated at runtime
    )

    sql = _dml_sql(dto_filter, dialect_name)

    assert "WHERE (EXISTS (SELECT 1 FROM fruit AS fruit_1 WHERE color.id = fruit_1.color_id" in sql
    assert ") OR color.name = " in sql
    assert "FROM color" not in sql


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite"])
def test_filter_expressions_aggregation_reads_a_copy_of_the_root(dialect_name: str) -> None:
    """A DML aggregation filter reads a root copy: a known old-planner exception, pending the user's decision."""
    aggregation_filter = _input_type(ColorFilter, "fruits_aggregate")
    count_filter = _input_type(aggregation_filter, "count")
    predicate = _input_type(count_filter, "predicate")
    dto_filter = ColorFilter(fruits_aggregate=aggregation_filter(count=count_filter(predicate=predicate(gt=2))))  # ty: ignore[unknown-argument]  # input fields are generated at runtime

    sql = _dml_sql(dto_filter, dialect_name)

    assert "WHERE EXISTS ( SELECT 1 FROM color AS color_1" in sql
    assert sql.endswith("AND color_1.id = color.id )")


def test_or_next_to_column_predicate_is_parenthesized() -> None:
    """An ``_or`` next to a column predicate is grouped, so that the predicate applies to both branches."""
    lines = plan_sql(
        '{ colors(filter: { name: { eq: "x" }, _or: [{ name: { eq: "a" } }, { name: { eq: "b" } }] }) { id } }',
        "sqlite",
    )

    assert _where(lines) == ["WHERE color.name = ?", "AND (color.name = ? OR color.name = ?)"]


def test_and_under_or_keeps_its_parentheses() -> None:
    """A multi-predicate ``_and`` branch of an ``_or`` is grouped, so that OR does not split it."""
    lines = plan_sql(
        '{ colors(filter: { _or: [{ _and: [{ name: { eq: "a" } }, { name: { neq: "c" } }] }, { name: { eq: "b" } }] }) '
        "{ id } }",
        "sqlite",
    )

    assert _where(lines) == ["WHERE (color.name = ? AND color.name != ?)", "OR color.name = ?"]


def test_predicates_next_to_or_are_grouped() -> None:
    """Several column predicates next to an ``_or`` are grouped apart from it."""
    lines = plan_sql(
        '{ colors(filter: { name: { eq: "x", neq: "y" }, _or: [{ name: { eq: "a" } }, { name: { eq: "b" } }] }) '
        "{ id } }",
        "sqlite",
    )

    assert _where(lines) == ["WHERE (color.name = ? AND color.name != ?)", "AND (color.name = ? OR color.name = ?)"]


@_DIALECTS
def test_two_split_ors_are_each_an_or_of_exists(dialect_name: str) -> None:
    """Two ``_or`` of a to-many branch and a root predicate are AND-ed, each its own EXISTS OR predicate."""
    lines = plan_sql(
        '{ colors(filter: { _and: [{ _or: [{ fruits: { sweetness: { gt: 5 } } }, { name: { eq: "red" } }] }, '
        '{ _or: [{ fruits: { name: { eq: "kiwi" } } }, { name: { eq: "blue" } }] }] }) { name } }',
        dialect_name,
    )

    where = _where(lines)
    assert len(where) == 2
    assert where[0].startswith("WHERE ((EXISTS (SELECT 1 FROM fruit AS fruit_1 WHERE color.id = fruit_1.color_id")
    assert where[1].startswith("AND ((EXISTS (SELECT 1 FROM fruit AS fruit_2 WHERE color.id = fruit_2.color_id")
    assert all(") OR color.name = " in line for line in where)
    assert _reads_in_exists(" ".join(where), "color") == 0


@_DIALECTS
def test_to_many_not_of_to_one_and_secondary_to_many_is_one_not_exists(dialect_name: str) -> None:
    """A to-many ``_not`` of a to-one and a secondary to-many is one NOT EXISTS reading both from the related row."""
    lines = plan_sql(_USERS_NOT_TAGGED_IN_UNNAMED_DEPARTMENT, dialect_name)

    where = " ".join(_where(lines))
    assert "AND NOT (EXISTS (SELECT 1 FROM tag AS tag_1, department AS department_1 " in where
    assert "WHERE tag_1.id = user_1.tag_id AND user_1.id = user_department_join_table_1.user_id" in where


def test_to_many_not_of_to_one_and_secondary_to_many_keeps_groups_with_a_passing_user(sqlite_session: Session) -> None:
    """A group passes a users ``_not`` of a tag and a department filter when one of its users fails either."""
    tag_x, tag_y, color = Tag(name="x", private=""), Tag(name="y", private=""), Color(name="c", private="")
    unnamed, named = Department(name=None, private=""), Department(name="d", private="")

    def user(tag: Tag | None, *departments: Department) -> User:
        return User(name="u", private="", tag=tag, departments=list(departments))

    users = {
        "no_user": [],
        "tagged_in_unnamed": [user(tag_x, unnamed)],
        "other_tag": [user(tag_y, unnamed)],
        "no_tag": [user(None, unnamed)],
        "named_department": [user(tag_x, named)],
        "one_passing": [user(tag_x, unnamed), user(tag_x)],
    }
    sqlite_session.add_all(
        Group(name=name, private="", tag=tag_x, color=color, users=group_users) for name, group_users in users.items()
    )
    sqlite_session.flush()

    names = _queried_names(sqlite_session, _USERS_NOT_TAGGED_IN_UNNAMED_DEPARTMENT, "groups")

    assert names == {"other_tag", "no_tag", "named_department", "one_passing"}


def test_aggregate_under_one_of_two_to_many_paths_joins_its_lateral_from_its_relation() -> None:
    """An EXISTS over two to-many paths, one counted, joins the count's LATERAL from the counted relation's row."""
    lines = plan_sql(
        "{ groups(filter: { users: { departmentsAggregate: { count: { predicate: { gt: 1 } } } }, "
        'color: { fruits: { name: { eq: "x" } } } }) { name } }',
        "postgresql",
    )

    exists = " ".join(line.strip() for line in lines)
    assert 'FROM "user" AS user_1 JOIN LATERAL ( SELECT count(*) AS count_1' in exists
    assert "WHERE user_1.id = user_department_join_table_1.user_id ) AS anon_1 ON TRUE" in exists
