"""Tests of CTE sharing on hand-built plans."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import exists, literal, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql import visitors
from sqlalchemy.sql.selectable import CTE

from strawchemy.config.databases import DatabaseFeatures
from strawchemy.transpiler._core.plan import QueryPlan
from strawchemy.transpiler._core.rowset import Join, Projection, RowSet
from strawchemy.transpiler._core.share import share_ctes
from tests.unit.models import Color, Fruit

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass

    from strawchemy.typing import QueryNodeType

_SQLITE = DatabaseFeatures(dialect="sqlite")


class _Node:
    def __init__(self, level: int = 0) -> None:
        self.level = level


def _node(level: int = 0) -> QueryNodeType:
    return cast("QueryNodeType", _Node(level))


def _fruit_cte(*, with_other: bool) -> tuple[CTE, list[AliasedClass[Any]]]:
    """Builds a CTE over fruit, joined to a second alias of fruit when ``with_other``, and an entity per alias."""
    fruit = aliased(Fruit, flat=True)
    columns: list[Any] = [fruit.id, fruit.color_id]
    statement = select(*columns).select_from(fruit)
    aliases = [fruit]
    if with_other:
        other = aliased(Fruit, flat=True)
        statement = statement.add_columns(other.id, other.color_id).join(other, other.color_id == fruit.color_id)
        aliases.append(other)
    cte = statement.cte()
    return cte, [cast("AliasedClass[Any]", aliased(alias, cte)) for alias in aliases]


def _plan(*, with_other: bool) -> QueryPlan:
    """Builds a plan joining two CTEs with identical bodies to the root, and projecting every entity over them."""
    color = cast("AliasedClass[Any]", aliased(Color, name="color"))
    projection = Projection.over(_node(), color)
    for _ in range(2):
        cte, entities = _fruit_cte(with_other=with_other)
        node = _node(1)
        projection = projection.with_join(Join(("relation", node), cte, cte.c.color_id == color.id, True, entities[0]))
        for entity in entities:
            projection = replace(projection, entities={**projection.entities, _node(1): entity})
    return QueryPlan(RowSet.over(color), projection, cast("Any", SimpleNamespace(db_features=_SQLITE)))


def test_identical_bodies_are_shared() -> None:
    """Two CTEs with identical bodies over one alias of fruit become one CTE and an alias of it."""
    plan = share_ctes(_plan(with_other=False))

    first, second = plan.projection.joins.values()
    assert second.target.element is first.target.element  # ty: ignore[unresolved-attribute]
    assert second.target is not first.target


def test_body_selecting_two_aliases_of_one_table_is_not_shared() -> None:
    """A CTE whose body selects two aliases of fruit keeps its own CTE: its entities cannot move unambiguously."""
    plan = _plan(with_other=True)

    assert share_ctes(plan) is plan


def test_subquery_reading_a_dropped_cte_reads_the_kept_cte() -> None:
    """A WHERE subquery reading the dropped CTE reads the alias of the kept CTE that replaces it."""
    plan = _plan(with_other=False)
    dropped = list(plan.projection.joins.values())[1].target
    plan = replace(plan, rows=plan.rows.with_where(exists(select(literal(1)).select_from(dropped))))

    shared = share_ctes(plan)

    second = list(shared.projection.joins.values())[1]
    read = [element for element in visitors.iterate(shared.rows.where[0]) if isinstance(element, CTE)]
    assert any(cte is second.target for cte in read)
    assert not any(cte is dropped for cte in read)
