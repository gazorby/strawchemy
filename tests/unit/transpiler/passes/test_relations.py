"""Tests for the ``Relations`` pass: joins of selected relations and the ORDER BY they add to their parent."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.dialects import postgresql

from strawchemy import Strawchemy
from strawchemy.config.databases import DatabaseFeatures
from strawchemy.dto.strawberry import QueryNode
from strawchemy.transpiler._core.level import Level, PlanContext
from strawchemy.transpiler._core.pipeline import Pipeline, Pipelines
from strawchemy.transpiler._core.request import QueryRequest
from strawchemy.transpiler._passes.relations import Relations, _shares, _sibling_groups
from strawchemy.transpiler.hook import QueryHook
from tests.unit.models import Color, User
from tests.unit.transpiler.passes.utils import outer_order_by, plan_sql
from tests.utils import as_dto

if TYPE_CHECKING:
    from strawchemy.transpiler._core.rowset import Projection, RowSet
    from strawchemy.typing import QueryNodeType

_strawchemy = Strawchemy("postgresql")


_EMPTY = Pipeline(())
_PIPELINES = Pipelines(root=_EMPTY, relation=_EMPTY, exists=_EMPTY, dml=_EMPTY)
_LATERAL = DatabaseFeatures("postgresql", supports_lateral=True)
_NO_LATERAL = DatabaseFeatures("sqlite", supports_lateral=False)


_DIALECTS = pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
_CTE_DIALECTS = pytest.mark.parametrize("dialect_name", ["sqlite", "mysql"])
_CTE = re.compile(r"\banon_\d+ AS \(")
_RANK = r"row_number\(\) OVER \(ORDER BY {}\) AS rank_\d+"
_CTE_RANK = r"dense_rank\(\) OVER \(PARTITION BY fruit_\d+\.color_id ORDER BY {}\) AS rank_\d+"


@_strawchemy.type(Color, include="all")
class _ColorType: ...


@_strawchemy.type(User, include="all")
class _UserType: ...


class _HookA(QueryHook[Color]): ...


class _HookB(QueryHook[Color]): ...


def _shared_sql(query: str) -> str:
    return "\n".join(plan_sql(query, "postgresql", literal_binds=True))


def _cte_sql(query: str, dialect_name: str) -> str:
    """Returns the SQL of ``query`` on one line, with MySQL's backticks written as SQLite's double quotes."""
    sql = " ".join(" ".join(plan_sql(query, dialect_name, literal_binds=True)).split())
    return sql.replace("`user`", '"user"').replace("`", "")


def _page_filter(sql: str) -> str:
    """Returns the WHERE of the shared LATERAL that keeps the rows inside a page, as one line."""
    match = re.search(r"\) AS anon_\d+\s+WHERE (.*?)\s+\) AS anon_\d+\s+ON true", sql, re.DOTALL | re.IGNORECASE)
    assert match is not None, sql
    return " ".join(match.group(1).split())


@_DIALECTS
def test_relations_nested_joined_flat(dialect_name: str) -> None:
    """A selected relation without ordering or pagination of its own is one plain LEFT OUTER JOIN."""
    lines = plan_sql("{ colors { fruits { name } } }", dialect_name)

    assert [line.strip() for line in lines if "JOIN" in line] == ["LEFT OUTER JOIN fruit AS fruit_1"]
    assert not any("LATERAL" in line or "WITH" in line for line in lines)


@_DIALECTS
def test_relations_order_parent_by_child_keys(dialect_name: str) -> None:
    """With deterministic ordering, a relation without ordering of its own orders the parent query by its keys."""
    lines = plan_sql("{ colors { fruits { name } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "fruit_1.id ASC"]


@_DIALECTS
def test_relations_order_outer_keys_before_nested_keys(dialect_name: str) -> None:
    """With deterministic ordering, each relation level's keys come after those of the level above it."""
    lines = plan_sql("{ colors { fruits { color { name } } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "fruit_1.id ASC", "color_1.id ASC"]


@_DIALECTS
def test_relations_own_order_comes_before_nested_keys(dialect_name: str) -> None:
    """A relation's own ordering, carried by its LATERAL or CTE, orders the query before the relations below it."""
    lines = plan_sql("{ colors { fruits(orderBy: { name: ASC }) { color { name } } } }", dialect_name)

    assert outer_order_by(lines) == ["color.id ASC", "anon_1.name ASC", "color_1.id ASC"]


@_DIALECTS
def test_relations_own_limit_uses_lateral_or_cte(dialect_name: str) -> None:
    """A relation with its own limit is a LATERAL join on postgresql, a CTE ranked by ``dense_rank`` otherwise."""
    sql = "\n".join(plan_sql("{ colorsPaginatedFruits { fruits(limit: 2) { name } } }", dialect_name))

    if dialect_name == "postgresql":
        assert "LEFT OUTER JOIN LATERAL" in sql
        assert "LIMIT" in sql
    else:
        assert sql.startswith("WITH")
        assert "dense_rank()" in sql
        assert "LATERAL" not in sql


@_DIALECTS
def test_same_model_two_paths_gets_two_aliases(dialect_name: str) -> None:
    """A model reached from the root and through a relation is read from two aliases, correlated differently."""
    lines = plan_sql("{ colors { fruits { color { name } } } }", dialect_name)

    assert "  FROM color AS color" in lines
    assert [line.strip() for line in lines if "JOIN" in line] == [
        "LEFT OUTER JOIN fruit AS fruit_1",
        "LEFT OUTER JOIN color AS color_1",
    ]


@_CTE_DIALECTS
def test_aliases_differing_in_limit_share_one_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, aliases of a relation differing only in limit join one rank CTE, once, with both bounds."""
    sql = _cte_sql(
        "{ colorsPaginatedFruits { a: fruits(limit: 2) { name } b: fruits(limit: 3) { name } } }", dialect_name
    )

    assert len(_CTE.findall(sql)) == 1
    assert sql.count("JOIN anon_1") == 1
    assert re.search(r"AND \((anon_1)\.(rank_\d+) <= 2 OR \1\.(rank_\d+) <= 3\)", sql)


@_CTE_DIALECTS
def test_small_page_aliases_share_one_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, two small pages share one rank CTE, ranked once per alias and joined on either page."""
    sql = _cte_sql(
        "{ colorsOrderedPaginatedFruits { id sourest: fruits(orderBy: { sweetness: ASC }, limit: 2) { name } "
        "sweetest: fruits(orderBy: { sweetness: DESC }, limit: 2) { name } } }",
        dialect_name,
    )

    assert len(_CTE.findall(sql)) == 1
    assert sql.count("FROM fruit AS") == 1
    assert sql.count("JOIN anon_1") == 1
    assert re.search(_CTE_RANK.format(r"fruit_\d+\.sweetness ASC.*?, fruit_\d+\.id ASC"), sql)
    assert re.search(_CTE_RANK.format(r"fruit_\d+\.sweetness DESC.*?, fruit_\d+\.id ASC"), sql)
    assert re.search(r"AND \((anon_1)\.(rank_\d+) <= 2 OR \1\.(rank_\d+) <= 2\)", sql)


@_CTE_DIALECTS
def test_unbounded_aliases_share_one_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, two orderings of every fruit share one rank CTE, joined without a page condition."""
    sql = _cte_sql(
        "{ colors { id sweetFirst: fruits(orderBy: { sweetness: DESC }) { name } "
        "sourFirst: fruits(orderBy: { sweetness: ASC }) { name } } }",
        dialect_name,
    )

    assert len(_CTE.findall(sql)) == 1
    assert sql.count("FROM fruit AS") == 1
    assert sql.count("JOIN anon_1") == 1
    assert len(re.findall(_CTE_RANK.format(".*?"), sql)) == 2
    assert not re.search(r"rank_\d+ [<>]", sql)


@_CTE_DIALECTS
def test_nested_selections_under_shared_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, selections under aliases sharing a rank CTE are one aggregate join and one to-one join."""
    sql = _cte_sql(
        "{ groupsOrderedUsers { id "
        "a: users(orderBy: { name: ASC }) { id departmentsAggregate { count } tag { name } } "
        "b: users(orderBy: { name: DESC }) { id departmentsAggregate { count } } } }",
        dialect_name,
    )

    assert sql.count("AS rank_1") == 1
    assert sql.count("JOIN department AS") == 1
    assert sql.count("count(*)") == 1
    assert sql.count("JOIN tag AS") == 1


@_CTE_DIALECTS
def test_two_paths_share_one_rank_cte_without_lateral(dialect_name: str) -> None:
    """Without LATERAL, a relation and the same relation reached through another path share one rank CTE."""
    sql = _cte_sql(
        "{ colors { id fruits(orderBy: { sweetness: DESC }) { sweetness "
        "color { fruits(orderBy: { sweetness: ASC }) { sweetness } } } } }",
        dialect_name,
    )

    assert len(_CTE.findall(sql)) == 1
    assert sql.count("FROM fruit AS") == 1
    assert re.search(_CTE_RANK.format(r"fruit_\d+\.sweetness DESC.*?, fruit_\d+\.id"), sql)
    assert re.search(_CTE_RANK.format(r"fruit_\d+\.sweetness ASC.*?, fruit_\d+\.id"), sql)
    assert re.search(r"JOIN anon_1 ON color\.id = anon_1\.color_id", sql)
    assert re.search(r"JOIN anon_1 AS anon_2 ON color_1\.id = anon_2\.color_id", sql)


def _fruits(
    root: QueryNodeType, *, limit: int | None = None, offset: int | None = None, distinct_on: tuple[object, ...] = ()
) -> QueryNodeType:
    node = root.insert_child(as_dto(_ColorType).__dto_field_definitions__["fruits"])
    node.metadata.data.relation_filter = type(node.metadata.data.relation_filter)(
        limit=limit, offset=offset, distinct_on=distinct_on
    )
    return node


def _level(root: QueryNodeType, query_hooks: dict[QueryNodeType, list[QueryHook[Color]]] | None = None) -> Level:
    request = QueryRequest(
        model=root.value.model,
        selection_tree=root,
        dto_filter=None,
        order_by=(),
        distinct_on=(),
        limit=None,
        offset=None,
        allow_null=False,
    )
    context = PlanContext.create(
        request.model, postgresql.dialect(), pipelines=_PIPELINES, query_hooks=query_hooks or {}
    )
    return Level.root(request, context)


def test_sibling_groups_group_by_relationship() -> None:
    """Aliases of one relationship form a group, in selection order; another relationship is a group of its own."""
    root = QueryNode.root_node(User)
    group_a = root.insert_child(as_dto(_UserType).__dto_field_definitions__["group"])
    tag = root.insert_child(as_dto(_UserType).__dto_field_definitions__["tag"])
    group_b = root.insert_child(as_dto(_UserType).__dto_field_definitions__["group"])
    group_b.metadata.data.relation_filter = type(group_b.metadata.data.relation_filter)(limit=1)

    assert _sibling_groups(_level(root)) == [(group_a, group_b), (tag,)]


def test_distinct_on_alias_leaves_the_group() -> None:
    """An alias with DISTINCT ON is a group of one, beside the group of the other aliases."""
    root = QueryNode.root_node(Color)
    first = _fruits(root, limit=1)
    distinct = _fruits(root, distinct_on=("name",))
    last = _fruits(root, limit=2)

    assert _sibling_groups(_level(root)) == [(first, last), (distinct,)]


def test_differing_hooks_leave_the_group() -> None:
    """An alias whose hooks differ from those of the group's first alias is a group of one."""
    root = QueryNode.root_node(Color)
    first, hooked, last = _fruits(root, limit=1), _fruits(root, limit=2), _fruits(root, limit=3)
    hooks: dict[QueryNodeType, list[QueryHook[Color]]] = {first: [_HookA()], hooked: [_HookB()], last: [_HookA()]}

    assert _sibling_groups(_level(root, hooks)) == [(first, last), (hooked,)]


def test_group_of_one_does_not_share() -> None:
    """A lone alias is planned on its own, whatever the database."""
    root = QueryNode.root_node(Color)

    assert not _shares((_fruits(root),), _NO_LATERAL)
    assert not _shares((_fruits(root),), _LATERAL)


def test_shares_without_lateral_always() -> None:
    """Without LATERAL, any group of several aliases shares one ranked CTE, bounded or not."""
    root = QueryNode.root_node(Color)

    assert _shares((_fruits(root, limit=1), _fruits(root, limit=1)), _NO_LATERAL)
    assert _shares((_fruits(root), _fruits(root)), _NO_LATERAL)


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        pytest.param([(2, None), (2, None)], False, id="2x2"),
        pytest.param([(4, None), (4, None)], False, id="4x4"),
        pytest.param([(5, None), (5, None)], True, id="5x5"),
        pytest.param([(2, None), (None, None)], True, id="unbounded-alias"),
        pytest.param([(None, None), (None, None)], True, id="unbounded"),
        pytest.param([(1, 1), (2, None)], False, id="offset-counts"),
        pytest.param([(2, None), (2, None), (2, None)], False, id="three-8"),
        pytest.param([(3, None), (3, None), (2, None)], True, id="three-18"),
    ],
)
def test_shares_on_lateral_unless_small_pages(pages: list[tuple[int | None, int | None]], expected: bool) -> None:
    """With LATERAL, a group stays separate only when every alias is bounded and the pages multiply to at most 16."""
    root = QueryNode.root_node(Color)
    group = tuple(_fruits(root, limit=limit, offset=offset) for limit, offset in pages)

    assert _shares(group, _LATERAL) is expected


def test_project_plans_a_sharing_group_at_its_first_member(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sharing group is planned once, where its first alias is selected; other relations keep their position."""
    root = QueryNode.root_node(User)
    first = root.insert_child(as_dto(_UserType).__dto_field_definitions__["group"])
    tag = root.insert_child(as_dto(_UserType).__dto_field_definitions__["tag"])
    last = root.insert_child(as_dto(_UserType).__dto_field_definitions__["group"])
    last.metadata.data.relation_filter = type(last.metadata.data.relation_filter)(limit=1)
    calls: list[tuple[str, tuple[QueryNodeType, ...]]] = []

    def plan_siblings(_: Level, nodes: tuple[QueryNodeType, ...], __: RowSet, projection: Projection) -> Projection:
        calls.append(("siblings", nodes))
        return projection

    def plan_child(_: Level, node: QueryNodeType, __: RowSet, projection: Projection) -> Projection:
        calls.append(("child", (node,)))
        return projection

    monkeypatch.setattr(Level, "plan_siblings", plan_siblings)
    monkeypatch.setattr(Level, "plan_child", plan_child)

    Relations().project(_level(root), object(), object())  # ty: ignore[invalid-argument-type]

    assert calls == [("siblings", (first, last)), ("child", (tag,))]


def test_project_plans_equal_siblings_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two aliases equal as nodes both reach ``plan_siblings``: none is dropped as a follower."""
    root = QueryNode.root_node(Color)
    first, second = _fruits(root), _fruits(root)
    calls: list[tuple[QueryNodeType, ...]] = []

    def plan_siblings(_: Level, nodes: tuple[QueryNodeType, ...], __: RowSet, projection: Projection) -> Projection:
        calls.append(nodes)
        return projection

    monkeypatch.setattr(Level, "plan_siblings", plan_siblings)

    Relations().project(_level(root), object(), object())  # ty: ignore[invalid-argument-type]

    assert len(calls) == 1
    assert [id(node) for node in calls[0]] == [id(first), id(second)]


def test_unbounded_aliases_share_one_lateral() -> None:
    """Two orderings of every fruit read ``fruit`` once, through one LATERAL ranking it once per alias."""
    sql = _shared_sql(
        "{ colors { id sweetFirst: fruits(orderBy: { sweetness: DESC }) { name } "
        "sourFirst: fruits(orderBy: { sweetness: ASC }) { name } } }"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert sql.count("FROM fruit AS") == 1
    assert re.search(_RANK.format(r"fruit_\d+\.sweetness DESC, fruit_\d+\.id ASC"), sql)
    assert re.search(_RANK.format(r"fruit_\d+\.sweetness ASC, fruit_\d+\.id ASC"), sql)
    assert "rank_1 <=" not in sql


def test_small_page_aliases_stay_separate() -> None:
    """Two pages of 2 fruits multiply to 4 rows at most, so each keeps its own index-backed LATERAL."""
    sql = _shared_sql(
        "{ colorsOrderedPaginatedFruits { id sourest: fruits(orderBy: { sweetness: ASC }, limit: 2) { name } "
        "sweetest: fruits(orderBy: { sweetness: DESC }, limit: 2) { name } } }"
    )

    assert sql.count("JOIN LATERAL") == 2
    assert "row_number()" not in sql


@pytest.mark.parametrize(("second_page", "laterals"), [("limit: 2", 2), ("limit: 2, offset: 1", 3)])
def test_small_page_aliases_next_to_their_aggregate_stay_separate(second_page: str, laterals: int) -> None:
    """Small pages next to the relation's aggregate keep a LATERAL per distinct page, beside the aggregate's own."""
    sql = _shared_sql(
        f"{{ colorsOrderedPaginatedFruits {{ id a: fruits(limit: 2) {{ name }} b: fruits({second_page}) {{ name }} "
        "fruitsAggregate { count } } }"
    )

    assert sql.count("JOIN LATERAL") == laterals
    assert "row_number()" not in sql


def test_bigger_pages_share_with_page_filter() -> None:
    """Pages multiplying to more than 16 rows share one LATERAL, which keeps the rows inside either page."""
    sql = _shared_sql(
        "{ colorsOrderedPaginatedFruits { id first: fruits(orderBy: { id: ASC }, limit: 5) { id } "
        "next: fruits(orderBy: { id: ASC }, limit: 5, offset: 5) { id } } }"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert sql.count("row_number()") == 2
    assert re.fullmatch(r"(anon_\d+)\.(rank_\d+) <= 5 OR \1\.(rank_\d+) > 5 AND \1\.\3 <= 10", _page_filter(sql))


@pytest.mark.parametrize("unbounded", ["limit: null", "limit: null, offset: 0"])
def test_one_unbounded_alias_drops_the_page_filter(unbounded: str) -> None:
    """An alias reading every fruit, from an offset of 0 or none, keeps every ranked row: no page filter."""
    sql = _shared_sql(
        "{ colorsOrderedPaginatedFruits { id topTwo: fruits(orderBy: { sweetness: DESC }, limit: 2) { name } "
        f"all: fruits({unbounded}) {{ name }} }} }}"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert sql.count("row_number()") == 2
    assert not re.search(r"WHERE .*rank_\d+ [<>]", sql)


def test_nested_selections_under_shared_aliases() -> None:
    """Selections under shared aliases are planned on the shared alias: one aggregate join, one to-one join."""
    sql = _shared_sql(
        "{ groupsOrderedUsers { id "
        "a: users(orderBy: { name: ASC }) { id departmentsAggregate { count } tag { name } } "
        "b: users(orderBy: { name: DESC }) { id departmentsAggregate { count } } } }"
    )

    assert sql.count('FROM "user" AS') == 1
    assert sql.count("FROM department AS") == 1
    assert sql.count("count(*)") == 1
    assert sql.count("JOIN tag AS") == 1


def test_aggregate_under_one_shared_alias() -> None:
    """An aggregate selected under one shared alias only is joined once, on the shared alias."""
    sql = _shared_sql(
        "{ groupsOrderedUsers { id a: users(orderBy: { name: ASC }) { id departmentsAggregate { count } } "
        "b: users(orderBy: { name: DESC }) { id } } }"
    )

    assert sql.count('FROM "user" AS') == 1
    assert sql.count("count(*)") == 1


def test_offset_without_limit_page() -> None:
    """An offset without limit keeps the ranks after the offset, and bounds the shared rows like a limit."""
    sql = _shared_sql(
        "{ colorsOrderedPaginatedFruits { id a: fruits(offset: 2, limit: null) { name } "
        "b: fruits(limit: 1) { name } } }"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert re.fullmatch(r"(anon_\d+)\.(rank_\d+) > 2 OR \1\.(rank_\d+) <= 1", _page_filter(sql))


def test_null_ordering_window() -> None:
    """A rank window orders on the terms of ``order_terms``, null placement included."""
    sql = _shared_sql(
        "{ colors { id a: fruits(orderBy: { sweetness: ASC_NULLS_FIRST }) { name } "
        "b: fruits(orderBy: { name: DESC }) { name } } }"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert re.search(_RANK.format(r"fruit_\d+\.sweetness ASC NULLS FIRST, fruit_\d+\.id ASC"), sql)


@pytest.mark.allow_duplicate_reads(
    reason="an alias ordered through a join of its own is not compared for sharing and keeps its own read"
)
def test_aliases_selecting_other_rows_stay_separate() -> None:
    """Aliases whose rows differ in more than their order and page keep one LATERAL each."""
    sql = _shared_sql(
        "{ colors { id a: fruits(orderBy: { color: { name: ASC } }) { id } "
        "b: fruits(orderBy: { sweetness: DESC }) { id } } }"
    )

    assert sql.count("JOIN LATERAL") == 2
    assert "row_number()" not in sql


@_CTE_DIALECTS
@pytest.mark.allow_duplicate_reads(
    reason="an alias ordered through a join of its own is not compared for sharing and keeps its own read"
)
def test_aliases_selecting_other_rows_keep_one_rank_cte_each(dialect_name: str) -> None:
    """Without LATERAL, aliases whose rows differ in more than their order and page keep one rank CTE each."""
    sql = _cte_sql(
        "{ colors { id a: fruits(orderBy: { color: { name: ASC } }) { id } "
        "b: fruits(orderBy: { sweetness: DESC }) { id } } }",
        dialect_name,
    )

    assert len(_CTE.findall(sql)) == 2
    assert "rank_1" not in sql


def test_nested_relations_under_shared_aliases() -> None:
    """A to-one and a to-many relation selected under both shared aliases are each joined once, on the shared alias."""
    to_one = _shared_sql(
        "{ colors { id a: fruits(orderBy: { sweetness: ASC }) { id color { name } } "
        "b: fruits(orderBy: { sweetness: DESC }) { id color { name } } } }"
    )
    to_many = _shared_sql(
        "{ groupsOrderedUsers { id a: users(orderBy: { name: ASC }) { id departments { id } } "
        "b: users(orderBy: { name: DESC }) { id departments { id } } } }"
    )

    assert to_one.count("FROM fruit AS") == 1
    assert to_one.count("JOIN color AS") == 1
    assert to_many.count('FROM "user" AS') == 1
    assert to_many.count("JOIN department AS") == 1


_DEEP_UNDER_ALIASES = (
    "{ groupsOrderedUsers { id "
    "a: users(orderBy: { name: ASC }) { id tag { id groups { id color { name } } groupsAggregate { count } } } "
    "b: users(orderBy: { name: DESC }) { id tag { id groups { id color { name } } groupsAggregate { count } } } } }"
)


def test_deep_relations_under_shared_aliases() -> None:
    """Relations and aggregates two and three levels under both shared aliases are each joined once."""
    sql = _shared_sql(_DEEP_UNDER_ALIASES)

    assert sql.count("JOIN LATERAL") == 2
    assert sql.count('FROM "user" AS') == 1
    assert sql.count("JOIN tag AS") == 1
    assert sql.count('JOIN "group" AS') == 1
    assert sql.count("JOIN color AS") == 1
    assert sql.count("count(*)") == 1


@_CTE_DIALECTS
def test_deep_relations_under_shared_rank_cte(dialect_name: str) -> None:
    """Without LATERAL, relations and aggregates deep under aliases sharing a rank CTE are each joined once."""
    sql = _cte_sql(_DEEP_UNDER_ALIASES, dialect_name)

    assert len(_CTE.findall(sql)) == 2
    assert sql.count("AS rank_1") == 1
    assert sql.count("JOIN tag AS") == 1
    assert len(re.findall(r'JOIN "?group"? AS', sql)) == 1
    assert sql.count("JOIN color AS") == 1
    assert sql.count("count(*)") == 1


_ALIASED_UNDER_ONE_ALIAS = (
    "{ colors { id a: fruits(orderBy: { id: ASC }) { id color { x: fruits { id } y: fruits(orderBy: { name: ASC }) "
    "{ id } } } b: fruits(orderBy: { id: DESC }) { id color { fruits { name } } } } }"
)


@pytest.mark.allow_duplicate_reads(
    reason="a relation that a shared alias also selects through aliases of its own keeps one read per alias"
)
@_DIALECTS
def test_relation_aliased_under_one_shared_alias_keeps_its_read(dialect_name: str) -> None:
    """A relation that one shared alias selects under aliases of its own is joined, for the other alias, on its own."""
    sql = " ".join(plan_sql(_ALIASED_UNDER_ONE_ALIAS, dialect_name, literal_binds=True))

    assert not re.search(r",\s+(fruit|color) AS", sql)


@pytest.mark.parametrize(
    ("a_order", "b_order"),
    [pytest.param("name: ASC", "name: DESC", id="differing"), pytest.param("name: ASC", "name: ASC", id="equal")],
)
@pytest.mark.allow_duplicate_reads(
    reason="a relation with an ordering of its own, nested under shared aliases, keeps one read per alias"
)
def test_nested_relations_with_arguments_keep_one_read_per_alias(a_order: str, b_order: str) -> None:
    """A relation ordered by its own arguments under each shared alias gets one LATERAL per alias."""
    sql = _shared_sql(
        f"{{ colors {{ id a: fruits(orderBy: {{ sweetness: ASC }}) {{ id color {{ fruits(orderBy: {{ {a_order} }}) "
        f"{{ id }} }} }} b: fruits(orderBy: {{ sweetness: DESC }}) {{ id color {{ fruits(orderBy: {{ {b_order} }}) "
        "{ id } } } } }"
    )

    assert sql.count("JOIN color AS") == 1
    assert sql.count("JOIN LATERAL") == 3


def test_hooked_aliases_share_one_lateral() -> None:
    """Aliases of a relation whose hook only filters share one LATERAL, filtered by the hook once."""
    # Pins that the QueryHooks pass builds hook edits as partials, which ``_same_rows`` compares by function and arguments.
    sql = _shared_sql(
        "{ colorsOrderedSweetFruits { id a: fruits(orderBy: { name: ASC }) { id } "
        "b: fruits(orderBy: { name: DESC }) { id } } }"
    )

    assert sql.count("JOIN LATERAL") == 1
    assert sql.count("fruit_1.sweetness > 5") == 1
    assert sql.count("row_number()") == 2


def test_aliases_hooked_with_a_limit_stay_separate() -> None:
    """Aliases of a relation whose hook limits its rows keep one LATERAL each, ordered and limited by the hook."""
    sql = _shared_sql(
        "{ colorsOrderedFirstFruits { id a: fruits(orderBy: { name: ASC }) { id } "
        "b: fruits(orderBy: { name: DESC }) { id } } }"
    )

    assert sql.count("JOIN LATERAL") == 2
    assert sql.count("LIMIT 3") == 2
    assert "row_number()" not in sql
