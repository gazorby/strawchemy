"""Tests for the LATERAL and CTE joins ``attach_rows`` and ``attach_grouped`` build."""

from __future__ import annotations

import warnings
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import aliased
from sqlalchemy.sql.compiler import FROM_LINTING

from strawchemy.config.databases import DatabaseFeatures
from strawchemy.exceptions import TranspilingError
from strawchemy.transpiler._core.attach import (
    RankWindow,
    attach_grouped,
    attach_rows,
    attach_shared_rows,
    correlate_relation,
)
from strawchemy.transpiler._core.rowset import AggregateJoin, Join, OrderPriority, RowSet
from tests.unit.models import Color, Department, Fruit, User
from tests.utils import format_sql

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select
    from sqlalchemy.engine import Dialect
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.elements import UnaryExpression

    from strawchemy.typing import QueryNodeType

POSTGRES = DatabaseFeatures.new("postgresql")
SQLITE = DatabaseFeatures.new("sqlite")
MYSQL = DatabaseFeatures.new("mysql")
_DIALECTS: dict[str, Dialect] = {
    "postgresql": postgresql.dialect(),
    "sqlite": sqlite.dialect(),
    "mysql": mysql.dialect(),
}


class _Node:
    level = 1
    value = SimpleNamespace(model_field=None)


def _node() -> QueryNodeType:
    return cast("QueryNodeType", _Node())


def _sql(statement: Select[Any], features: DatabaseFeatures) -> str:
    """Compiles with the FROM linter on, so a cartesian product raises."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", category=SAWarning)
        compiled = statement.compile(
            dialect=_DIALECTS[features.dialect], compile_kwargs={"literal_binds": True}, linting=FROM_LINTING
        )
    return " ".join(format_sql(str(compiled)).split())


def _outer(
    parent: AliasedClass[Any],
    join: Join,
    *columns: ColumnElement[Any],
    order_by: Sequence[UnaryExpression[Any]] = (),
) -> Select[Any]:
    return (
        select(parent.id, *columns)
        .select_from(parent)
        .join(join.target, join.onclause, isouter=join.is_outer)
        .order_by(*order_by)
    )


def _fruits(*, limit: int | None = None, offset: int | None = None) -> tuple[Any, Any, RowSet]:
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    rows = RowSet.over(target).with_order_by(OrderPriority.CLIENT, target.sweetness.asc())
    return parent, target, replace(rows, limit=limit, offset=offset)


def test_attach_rows_lateral_correlates_on_the_foreign_key() -> None:
    """With LATERAL support the relation becomes a LATERAL joined ON TRUE and correlated in WHERE."""
    parent, target, rows = _fruits(limit=2, offset=1)
    node = _node()

    join, _ = attach_rows(rows, node, [target.name, target.id], Color.fruits, parent, POSTGRES, is_outer=True)

    assert join.key == ("relation", node)
    assert join.is_outer is True
    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name), POSTGRES)
    assert "LEFT OUTER JOIN LATERAL (" in sql
    assert "WHERE color.id = fruit_1.color_id" in sql
    assert "ORDER BY fruit_1.sweetness ASC LIMIT 2 OFFSET 1" in sql
    assert sql.endswith(") AS anon_1 ON TRUE")


def test_attach_rows_lateral_returns_the_order_by_adapted_onto_the_lateral() -> None:
    """The returned ORDER BY terms read columns of the LATERAL, which exposes the ones it orders by."""
    parent, target, rows = _fruits()
    join, order_by = attach_rows(rows, _node(), [target.name], Color.fruits, parent, POSTGRES, is_outer=True)

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name, order_by=order_by), POSTGRES)

    assert "fruit_1.sweetness AS sweetness" in sql
    assert sql.endswith("ORDER BY anon_1.sweetness ASC")


def test_attach_rows_cte_ranks_per_parent_and_limits_in_on() -> None:
    """Without LATERAL the relation is a CTE ranked per foreign key, limit and offset applied in ON."""
    parent, target, rows = _fruits(limit=2, offset=1)

    join, order_by = attach_rows(rows, _node(), [target.name, target.id], Color.fruits, parent, SQLITE, is_outer=True)

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name, order_by=order_by), SQLITE)
    assert "dense_rank() OVER (PARTITION BY fruit_1.color_id ORDER BY fruit_1.sweetness ASC, fruit_1.id)" in sql
    assert "WHERE fruit_1.color_id IS NOT NULL" in sql
    assert "LIMIT" not in sql
    assert "ON color.id = anon_1.color_id AND anon_1.rank > 1 AND anon_1.rank <= 3" in sql
    assert sql.endswith("ORDER BY anon_1.sweetness ASC")


def test_attach_rows_cte_without_pagination_has_no_rank() -> None:
    """A relation without ordering, limit or offset gets a plain CTE joined on the foreign key."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")

    join, order_by = attach_rows(
        RowSet.over(target), _node(), [target.name], Color.fruits, parent, SQLITE, is_outer=True
    )

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name), SQLITE)
    assert "rank" not in sql
    assert order_by == ()
    assert "ON color.id = anon_1.color_id" in sql


def test_attach_rows_secondary_relation_joins_the_secondary_table() -> None:
    """A LATERAL through a secondary table joins it in the subquery instead of correlating it in WHERE."""
    parent = aliased(User.__mapper__, name="user")
    target = aliased(Department.__mapper__, name="department_1")
    rows = RowSet.over(target).with_order_by(OrderPriority.CLIENT, target.id.asc())

    join, _ = attach_rows(rows, _node(), [target.id, target.name], User.departments, parent, POSTGRES, is_outer=True)

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name), POSTGRES)
    assert (
        "FROM department AS department_1 JOIN user_department_join_table AS user_department_join_table_1 "
        "ON department_1.id = user_department_join_table_1.department_id"
    ) in sql
    assert 'WHERE "user".id = user_department_join_table_1.user_id' in sql


def test_attach_rows_emulated_distinct_on_is_ranked_per_database() -> None:
    """Emulated DISTINCT ON is ranked inside a LATERAL, and also per parent key inside a CTE."""
    parent, target, rows = _fruits(limit=1)
    rows = replace(rows, distinct_on=(target.name,))
    sqlite_join, _ = attach_rows(rows, _node(), [target.id], Color.fruits, parent, SQLITE, is_outer=True)
    lateral_join, _ = attach_rows(rows, _node(), [target.id], Color.fruits, parent, POSTGRES, is_outer=True)

    cte_sql = _sql(_outer(parent, sqlite_join), SQLITE)
    lateral_sql = _sql(_outer(parent, lateral_join), POSTGRES)

    assert "row_number() OVER (PARTITION BY fruit_1.color_id, fruit_1.name" in cte_sql
    assert "row_number() OVER (PARTITION BY fruit_1.name" in lateral_sql
    assert "WHERE color.id = fruit_1.color_id" in lateral_sql


def test_attach_rows_cte_nested_sort_keys_are_exposed() -> None:
    """The ORDER BY of a CTE relation reads the sort keys its own joins add, from columns the CTE exposes."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    nested = aliased(Color.__mapper__, name="color_1")
    node = _node()
    rows = RowSet.over(target).with_join(Join(("relation", node), nested, nested.id == target.color_id, True, nested))
    rows = rows.with_order_by(OrderPriority.CLIENT, nested.name.asc()).with_order_by(
        OrderPriority.CLIENT, target.sweetness.asc()
    )

    join, order_by = attach_rows(rows, _node(), [target.name], Color.fruits, parent, MYSQL, is_outer=True)

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name, order_by=order_by), MYSQL)
    assert "color_1.name AS name_1" in sql
    assert sql.endswith("ORDER BY anon_1.name_1 ASC, anon_1.sweetness ASC")


def test_attach_grouped_lateral_count() -> None:
    """On PostgreSQL an aggregate is a LATERAL of the function columns, correlated on the foreign key."""
    parent = aliased(Color.__mapper__, name="color")
    function_alias = aliased(Fruit.__mapper__, name="fruit_2")
    node, function_node = _node(), _node()
    label = func.count().label("count_1")

    join = attach_grouped({function_node: label}, node, Color.fruits, parent, function_alias, POSTGRES)

    assert isinstance(join, AggregateJoin)
    assert join.key == ("aggregate", node)
    sql = _sql(_outer(parent, join, join.columns[function_node]), POSTGRES)
    assert (
        "JOIN LATERAL ( SELECT count(*) AS count_1 FROM fruit AS fruit_2 WHERE color.id = fruit_2.color_id ) AS anon_1 ON TRUE"
        in sql
    )
    assert "coalesce" not in sql


def test_attach_grouped_cte_count_is_coalesced_in_an_outer_join() -> None:
    """On SQLite an aggregate is a CTE grouped by the foreign key, LEFT OUTER joined, counts coalesced to 0."""
    parent = aliased(Color.__mapper__, name="color")
    function_alias = aliased(Fruit.__mapper__, name="fruit_2")
    function_node = _node()
    label = func.count().label("count_1")

    join = attach_grouped({function_node: label}, _node(), Color.fruits, parent, function_alias, SQLITE)

    assert join.is_outer is True
    sql = _sql(_outer(parent, join, join.columns[function_node]), SQLITE)
    assert "GROUP BY fruit_2.color_id" in sql
    assert "WHERE fruit_2.color_id IS NOT NULL" in sql
    assert "LEFT OUTER JOIN anon_1 ON color.id = anon_1.color_id" in sql
    assert "coalesce(anon_1.count_1, 0)" in sql


def test_attach_grouped_cte_keeps_other_functions_uncoalesced() -> None:
    """Only counts are coalesced: a max stays the bare CTE column."""
    parent = aliased(Color.__mapper__, name="color")
    function_alias = aliased(Fruit.__mapper__, name="fruit_2")
    count_node, max_node = _node(), _node()
    labels = {count_node: func.count().label("count_1"), max_node: func.max(function_alias.sweetness).label("max_1")}

    join = attach_grouped(labels, _node(), Color.fruits, parent, function_alias, SQLITE)

    sql = _sql(_outer(parent, join, join.columns[count_node], join.columns[max_node]), SQLITE)
    assert "coalesce(anon_1.count_1, 0)" in sql
    assert "coalesce(anon_1.max_1" not in sql


def test_attach_grouped_secondary_uses_parent_copy_keys() -> None:
    """A CTE through a secondary table joins from its own copy of the parent and groups by the parent keys."""
    parent = aliased(User.__mapper__, name="user")
    function_alias = aliased(Department.__mapper__, name="department_1")
    function_node = _node()
    label = func.count().label("count_1")

    join = attach_grouped({function_node: label}, _node(), User.departments, parent, function_alias, SQLITE)

    sql = _sql(_outer(parent, join, join.columns[function_node]), SQLITE)
    assert join.is_outer is True
    assert "FROM USER AS user_1 JOIN user_department_join_table AS user_department_join_table_1" in sql
    assert "GROUP BY user_1.id" in sql
    assert "LEFT OUTER JOIN anon_1 ON user.id = anon_1.id" in sql
    assert "coalesce(anon_1.count_1, 0)" in sql


def test_attach_grouped_secondary_lateral_joins_the_secondary_table() -> None:
    """A LATERAL aggregate through a secondary table joins the target in the subquery, correlated on the parent key."""
    parent = aliased(User.__mapper__, name="user")
    function_alias = aliased(Department.__mapper__, name="department_1")
    function_node = _node()

    join = attach_grouped(
        {function_node: func.count().label("count_1")}, _node(), User.departments, parent, function_alias, POSTGRES
    )

    sql = _sql(_outer(parent, join, join.columns[function_node]), POSTGRES)
    assert (
        "JOIN LATERAL ( SELECT count(*) AS count_1 FROM department AS department_1 "
        "JOIN user_department_join_table AS user_department_join_table_1 "
        "ON department_1.id = user_department_join_table_1.department_id"
    ) in sql
    assert 'WHERE "user".id = user_department_join_table_1.user_id' in sql


def test_attach_grouped_lateral_correlates_from_a_nested_select() -> None:
    """A LATERAL aggregate joined in a subquery that does not read the parent still correlates to the parent."""
    parent = aliased(Color.__mapper__, name="color")
    fruit = aliased(Fruit.__mapper__, name="fruit_1")
    function_alias = aliased(Fruit.__mapper__, name="fruit_2")
    function_node = _node()
    join = attach_grouped(
        {function_node: func.count().label("count_1")}, _node(), Color.fruits, parent, function_alias, POSTGRES
    )
    body = select(fruit.id).join(join.target, join.onclause).where(parent.id == fruit.color_id)

    sql = _sql(select(parent.id).where(body.exists().correlate(parent)), POSTGRES)

    assert "SELECT count(*) AS count_1 FROM fruit AS fruit_2 WHERE color.id = fruit_2.color_id" in sql


def test_correlate_relation_secondary_keeps_target_left_of_later_joins() -> None:
    """A relation through a secondary table leaves its target as the left side of a join from the target."""
    parent = aliased(User.__mapper__, name="user")
    department = aliased(Department.__mapper__, name="department_1")
    user = aliased(User.__mapper__, name="user_1")
    relation = parent.departments.of_type(department)

    statement = correlate_relation(select(department.id), relation, department).join(
        user, department.users.of_type(user)
    )

    sql = _sql(select(parent.id).where(statement.exists().correlate(parent)), POSTGRES)
    assert sql.count("FROM department AS department_1 JOIN user_department_join_table") == 1
    assert 'WHERE "user".id = user_department_join_table_1.user_id' in sql


def test_attach_rows_lateral_nested_sort_keys_are_exposed() -> None:
    """The ORDER BY of a LATERAL relation reads the sort keys of its nested join and aggregate from the LATERAL."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    nested = aliased(Color.__mapper__, name="color_1")
    nested_fruits = aliased(Fruit.__mapper__, name="fruit_2")
    join_node, aggregate_node, function_node = _node(), _node(), _node()
    aggregate = attach_grouped(
        {function_node: func.count().label("count_1")}, aggregate_node, Color.fruits, nested, nested_fruits, POSTGRES
    )
    rows = (
        RowSet.over(target)
        .with_join(Join(("relation", join_node), nested, nested.id == target.color_id, True, nested))
        .with_join(aggregate)
        .with_order_by(OrderPriority.CLIENT, nested.name.asc())
        .with_order_by(OrderPriority.CLIENT, aggregate.columns[function_node].desc())
        .with_order_by(OrderPriority.CLIENT, target.sweetness.asc())
    )

    join, order_by = attach_rows(rows, _node(), [target.name], Color.fruits, parent, POSTGRES, is_outer=True)

    assert join.alias is not None
    sql = _sql(_outer(parent, join, join.alias.name, order_by=order_by), POSTGRES)
    assert "LEFT OUTER JOIN LATERAL (" in sql
    assert "color_1.name AS name_1" in sql
    assert sql.endswith("ORDER BY anon_1.name_1 ASC, anon_1.count_1 DESC, anon_1.sweetness ASC")


def test_attach_rows_secondary_relation_without_lateral_is_unsupported() -> None:
    """A secondary-table relation with its own plan on a database without LATERAL raises a TranspilingError."""
    parent = aliased(User.__mapper__, name="user")
    target = aliased(Department.__mapper__, name="department_1")
    rows = RowSet.over(target).with_order_by(OrderPriority.CLIENT, target.id.asc())

    with pytest.raises(TranspilingError, match="without LATERAL"):
        attach_rows(rows, _node(), [target.id], User.departments, parent, SQLITE, is_outer=True)


def test_attach_shared_rows_lateral_pages() -> None:
    """One LATERAL ranks the rows once per window, keeps those inside a page, and each page reads its rank from it."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    first, second = _node(), _node()
    windows = [
        RankWindow(first, (target.sweetness.asc(),), None, 2),
        RankWindow(second, (target.sweetness.desc(),), 5, 5),
    ]

    join, pages = attach_shared_rows(
        RowSet.over(target), windows, [target.name, target.id], Color.fruits, parent, POSTGRES, is_outer=True
    )

    assert join.key == ("relation", first)
    assert join.is_outer is True
    assert join.alias is not None
    assert inspect(join.alias).selectable is join.target
    assert [(page.offset, page.limit) for page in pages.values()] == [(None, 2), (5, 5)]
    assert all(any(page.rank is column for column in join.target.c) for page in pages.values())
    sql = _sql(_outer(parent, join, join.alias.name, *(page.rank for page in pages.values())), POSTGRES)
    assert "WHERE color.id = fruit_1.color_id" in sql
    assert "row_number() OVER (ORDER BY fruit_1.sweetness ASC, fruit_1.id ASC) AS rank_1" in sql
    assert "row_number() OVER (ORDER BY fruit_1.sweetness DESC, fruit_1.id ASC) AS rank_2" in sql
    assert "WHERE anon_2.rank_1 <= 2 OR anon_2.rank_2 > 5 AND anon_2.rank_2 <= 10" in sql
    assert sql.endswith(") AS anon_1 ON TRUE")


def test_attach_shared_rows_unbounded_window_keeps_every_row() -> None:
    """A window without offset or limit needs every ranked row: the LATERAL is the ranked SELECT itself."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    windows = [
        RankWindow(_node(), (target.sweetness.asc(),), None, 2),
        RankWindow(_node(), (target.id.asc(),), None, None),
    ]

    join, _ = attach_shared_rows(
        RowSet.over(target), windows, [target.id], Color.fruits, parent, POSTGRES, is_outer=True
    )

    sql = _sql(_outer(parent, join), POSTGRES)
    assert sql.count("SELECT") == 2
    assert "rank_1 <=" not in sql


def test_attach_shared_rows_cte_pages() -> None:
    """Without LATERAL, one CTE ranks the rows once per window per parent, joined on the OR of the pages."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    first, second = _node(), _node()
    windows = [
        RankWindow(first, (target.sweetness.asc(),), None, 2),
        RankWindow(second, (target.sweetness.desc(),), 5, 5),
    ]

    join, pages = attach_shared_rows(
        RowSet.over(target), windows, [target.name, target.id], Color.fruits, parent, SQLITE, is_outer=True
    )

    assert join.key == ("relation", first)
    assert join.is_outer is True
    assert join.alias is not None
    cte = inspect(join.alias).selectable
    assert [(page.offset, page.limit) for page in pages.values()] == [(None, 2), (5, 5)]
    assert all(any(page.rank is column for column in cte.c) for page in pages.values())
    sql = _sql(_outer(parent, join, join.alias.name, *(page.rank for page in pages.values())), SQLITE)
    assert sql.count("dense_rank()") == 2
    assert (
        "dense_rank() OVER (PARTITION BY fruit_1.color_id ORDER BY fruit_1.sweetness ASC, fruit_1.id ASC) AS rank_1"
        in sql
    )
    assert (
        "dense_rank() OVER (PARTITION BY fruit_1.color_id ORDER BY fruit_1.sweetness DESC, fruit_1.id ASC) AS rank_2"
        in sql
    )
    assert sql.endswith(
        "ON color.id = anon_1.color_id AND (anon_1.rank_1 <= 2 OR anon_1.rank_2 > 5 AND anon_1.rank_2 <= 10)"
    )


def test_attach_shared_rows_cte_unbounded_window_keeps_every_row() -> None:
    """Without LATERAL, a window without offset or limit joins every ranked row, on the relationship alone."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    windows = [
        RankWindow(_node(), (target.sweetness.asc(),), None, 2),
        RankWindow(_node(), (target.id.asc(),), None, None),
    ]

    join, pages = attach_shared_rows(
        RowSet.over(target), windows, [target.id], Color.fruits, parent, SQLITE, is_outer=True
    )

    sql = _sql(_outer(parent, join), SQLITE)
    assert sql.count("dense_rank()") == 2
    assert sql.endswith("ON color.id = anon_1.color_id")
    assert [(page.offset, page.limit) for page in pages.values()] == [(None, 2), (None, None)]


def test_attach_shared_rows_cte_offset_without_limit() -> None:
    """Without LATERAL, a window with an offset and no limit keeps the ranks after the offset inside the OR."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    windows = [
        RankWindow(_node(), (target.sweetness.asc(),), None, 2),
        RankWindow(_node(), (target.id.asc(),), 3, None),
    ]

    join, _ = attach_shared_rows(RowSet.over(target), windows, [target.id], Color.fruits, parent, SQLITE, is_outer=True)

    assert _sql(_outer(parent, join), SQLITE).endswith(
        "ON color.id = anon_1.color_id AND (anon_1.rank_1 <= 2 OR anon_1.rank_2 > 3)"
    )


def test_attach_shared_rows_ranks_equal_nodes_once() -> None:
    """Two windows of one node, whose arguments and so whose windows are equal, share one rank column."""
    parent = aliased(Color.__mapper__, name="color")
    target = aliased(Fruit.__mapper__, name="fruit_1")
    node = _node()
    windows = [RankWindow(node, (target.id.asc(),), None, None), RankWindow(node, (target.id.asc(),), None, None)]

    join, pages = attach_shared_rows(
        RowSet.over(target), windows, [target.id], Color.fruits, parent, POSTGRES, is_outer=True
    )

    assert list(pages) == [node]
    sql = _sql(_outer(parent, join), POSTGRES)
    assert sql.count("row_number()") == 1
    assert "row_number() OVER (ORDER BY fruit_1.id ASC) AS rank_1" in sql
