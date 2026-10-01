"""The division of a level's filter into the predicates its rows apply and the branches tested in an EXISTS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

from strawchemy.dto.strawberry import ExistsFilter, Filter, NotExistsFilter

if TYPE_CHECKING:
    from strawchemy.dto.strawberry import BooleanFilterDTO
    from strawchemy.typing import QueryNodeType

__all__ = ("FilterScope", "FilterSplit", "split_filter")


FilterScope: TypeAlias = Literal["query", "exists", "dml"]


@dataclass(frozen=True)
class FilterSplit:
    """A filter divided into the part applied on the rows directly and the part tested in an EXISTS."""

    direct: Filter | None = None
    """Predicates the rows stage applies directly."""
    exists: BooleanFilterDTO | None = None
    """Branches on relations, tested in an EXISTS so that they neither join nor repeat the rows."""
    join_path: tuple[QueryNodeType, ...] = ()
    """Relations inner-joined once for every predicate of ``direct``."""
    rows_filters: tuple[tuple[ExistsFilter, Filter], ...] = ()
    """EXISTS leaves of ``direct`` whose EXISTS would read a copy of their node, each with its filter on the rows."""

    def rows_filter(self, leaf: ExistsFilter) -> Filter | None:
        """Returns the filter testing ``leaf`` on the rows, if it is not tested in its own EXISTS."""
        return next((query_filter for tested, query_filter in self.rows_filters if tested is leaf), None)

    def filters(self) -> tuple[Filter, ...]:
        """Returns ``direct`` and the filters of ``rows_filters``, every predicate the rows stage applies."""
        direct = () if self.direct is None else (self.direct,)
        return (*direct, *(query_filter for _, query_filter in self.rows_filters))


def _filters_in_exists(tree: QueryNodeType, query_filter: Filter, scope: FilterScope) -> bool:
    fields = [node.value for node in tree.iter_breadth_first() if not node.is_root]
    if scope == "dml":
        return any(field.is_relation for field in fields) or any(
            isinstance(leaf, ExistsFilter) for leaf in query_filter.iter_leaves()
        )
    if scope == "exists":
        return any(map(_joins_relation, tree.children))
    return any(field.uselist and not field.is_computed for field in fields)


def _joins_relation(node: QueryNodeType) -> bool:
    return node.value.is_relation and not node.value.is_computed


def _reads_level_rows(dto_filter: BooleanFilterDTO) -> bool:
    """Tells whether an EXISTS testing ``dto_filter`` would read its root's rows rather than only its relations.

    It would when it outer-joins a relation leaving the root, aggregates one, or holds such an EXISTS on the root.
    """
    tree, query_filter = dto_filter.filters_tree()
    required = set(query_filter.join_path())
    if any(child.value.is_aggregate or (_joins_relation(child) and child not in required) for child in tree.children):
        return True
    return any(
        _reads_level_rows(leaf.dto_filter)
        for leaf in query_filter.iter_leaves()
        if isinstance(leaf, ExistsFilter) and leaf.field_node.is_root
    )


def _rows_filters(query_filter: Filter, scope: FilterScope) -> tuple[tuple[ExistsFilter, Filter], ...]:
    """Finds the EXISTS leaves of ``query_filter`` that would read a copy of their node, and builds their rows filter."""
    if scope == "dml":
        return ()
    found: list[tuple[ExistsFilter, Filter]] = []
    pending = [query_filter]
    while pending:
        current = pending.pop()
        pending.extend(value for value in current.and_ if isinstance(value, Filter))
        pending.extend(current.or_)
        pending.extend(() if current.not_ is None else (current.not_,))
        for leaf in current.and_:
            if isinstance(leaf, ExistsFilter) and _reads_level_rows(leaf.dto_filter):
                rows_filter = _branch_filter(leaf.dto_filter, leaf.field_node, scope)
                found.append((leaf, rows_filter))
                pending.append(rows_filter)
    return tuple(found)


def _split_conjuncts(
    dto_filter: BooleanFilterDTO, scope: FilterScope
) -> tuple[list[BooleanFilterDTO], list[BooleanFilterDTO], list[BooleanFilterDTO]]:
    """Sorts the top-level AND branches into those tested on the rows, in one EXISTS, and split at their EXISTS."""
    root_parts: list[BooleanFilterDTO] = []
    exists_parts: list[BooleanFilterDTO] = []
    split_parts: list[BooleanFilterDTO] = []
    for part in dto_filter.conjuncts():
        in_exists = _filters_in_exists(*part.filters_tree(), scope)
        if in_exists and (part.or_ or part.not_) and _reads_level_rows(part):
            split_parts.append(part)
        else:
            (exists_parts if in_exists else root_parts).append(part)
    return root_parts, exists_parts, split_parts


def _add_split(query_filter: Filter, part: BooleanFilterDTO, node: QueryNodeType, scope: FilterScope) -> None:
    """Adds ``part``, an ``_or`` branch each of whose branches is split on its own, or a ``_not`` as a NOT EXISTS.

    ``EXISTS(A OR B)`` is ``EXISTS(A) OR EXISTS(B)``, and ``EXISTS(B)`` is ``B`` when ``B`` reads only the rows.
    """
    if part.or_:
        branches = [_branch_filter(branch, node, scope) for branch in part.or_ if branch.has_filter()]
        if query_filter.or_:
            query_filter.and_.append(Filter(or_=branches))
        else:
            query_filter.or_ = branches
        return
    assert part.not_ is not None
    query_filter.and_.append(NotExistsFilter(dto_filter=part.not_, field_node=node))


def _branch_filter(branch: BooleanFilterDTO, node: QueryNodeType, scope: FilterScope) -> Filter:
    """Builds the filter of ``branch`` on the rows of ``node``, its parts needing a relation in one EXISTS."""
    root_parts, exists_parts, split_parts = _split_conjuncts(branch, scope)
    query_filter = branch.all_of(root_parts).filters_tree(node)[1]
    if exists_parts:
        query_filter.and_.append(ExistsFilter(dto_filter=branch.all_of(exists_parts), field_node=node))
    for part in split_parts:
        _add_split(query_filter, part, node, scope)
    return query_filter


def split_filter(dto_filter: BooleanFilterDTO | None, scope: FilterScope) -> FilterSplit:
    """Divides ``dto_filter`` for ``scope``: top-level AND branches that must be tested in an EXISTS move apart.

    An EXISTS that would read the rows of its root (outer-join a relation leaving it, or aggregate it) is split
    instead: each branch on a relation gets its own EXISTS, the others are tested on the rows.
    """
    if dto_filter is None:
        return FilterSplit()
    root_parts, exists_parts, split_parts = _split_conjuncts(dto_filter, scope)
    if scope == "exists":
        root_parts, exists_parts = [*root_parts, *exists_parts], []
    if not exists_parts and not split_parts:
        query_filter = dto_filter.filters_tree()[1]
        return FilterSplit(
            direct=query_filter,
            join_path=tuple(query_filter.join_path()),
            rows_filters=_rows_filters(query_filter, scope),
        )
    if not root_parts and not split_parts:
        return FilterSplit(exists=dto_filter)
    join_tree, query_filter = dto_filter.all_of(root_parts).filters_tree()
    for part in split_parts:
        _add_split(query_filter, part, join_tree, scope)
    return FilterSplit(
        direct=query_filter,
        exists=dto_filter.all_of(exists_parts) if exists_parts else None,
        join_path=tuple(query_filter.join_path()),
        rows_filters=_rows_filters(query_filter, scope),
    )
