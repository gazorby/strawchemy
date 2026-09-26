from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias, cast

from sqlalchemy import (
    CTE,
    BooleanClauseList,
    Label,
    Lateral,
    Select,
    UnaryExpression,
    inspect,
    null,
    select,
)
from sqlalchemy.orm import (
    QueryableAttribute,
    RelationshipDirection,
    RelationshipProperty,
    aliased,
)
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.visitors import iterate
from typing_extensions import Self

from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.dto.strawberry import (
    BooleanFilterDTO,
    EnumDTO,
    ExistsFilter,
    Filter,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)
from strawchemy.exceptions import TranspilingError
from strawchemy.repository.typing import DeclarativeT, OrderBySpec
from strawchemy.transpiler._aliasing import same_column
from strawchemy.transpiler._plan import add_missing_columns
from strawchemy.utils.graph import merge_trees

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql._typing import _OnClauseArgument
    from sqlalchemy.sql.selectable import NamedFromClause

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler import ColumnLoadingMode, QueryHook
    from strawchemy.transpiler._aliasing import AliasContext
    from strawchemy.typing import QueryNodeType

__all__ = ("AggregationJoin", "AggregationSpec", "Conjunction", "DistinctOn", "Join", "OrderBy", "QueryGraph", "Where")

FilterScope: TypeAlias = Literal["query", "subquery", "dml"]


@dataclass
class Join:
    """A join to a relation of the query, ordered by the depth of its node."""

    target: QueryableAttribute[Any] | NamedFromClause | AliasedClass[Any] | CTE | Lateral
    node: QueryNodeType
    onclause: _OnClauseArgument | None = None
    is_outer: bool = False
    order_by: list[OrderBySpec] = dataclasses.field(default_factory=list)
    """Client ordering of the relation, on columns of ``selectable``."""
    hook_order_by: tuple[UnaryExpression[Any], ...] = ()
    """ORDER BY of the relation's query hooks, read from the join target."""

    @property
    def _relationship(self) -> RelationshipProperty[Any]:
        """Relationship of the joined node."""
        return cast("RelationshipProperty[Any]", self.node.value.model_field.property)

    @property
    def selectable(self) -> NamedFromClause:
        """FROM clause of the join target."""
        if isinstance(self.target, AliasedClass):
            return cast("NamedFromClause", inspect(self.target).selectable)
        return cast("NamedFromClause", self.target)

    @property
    def order(self) -> int:
        """Depth of the joined node, used to join parents before children."""
        return self.node.level

    @property
    def to_many(self) -> bool:
        """Whether the joined relationship is one-to-many or many-to-many."""
        return self._relationship.direction in {
            RelationshipDirection.MANYTOMANY,
            RelationshipDirection.ONETOMANY,
        }

    def __gt__(self, other: Self) -> bool:
        return self.order > other.order

    def __lt__(self, other: Self) -> bool:
        return self.order < other.order

    def __le__(self, other: Self) -> bool:
        return self.order <= other.order

    def __ge__(self, other: Self) -> bool:
        return self.order >= other.order


@dataclass(kw_only=True)
class AggregationJoin(Join):
    """A join computing aggregates, told apart from relation joins with ``isinstance``."""


@dataclass
class AggregationSpec:
    """Every aggregate function one aggregation node needs, so that its join is built once.

    The filter, the ordering and the selection may use the same function; it is stored once under its function node.
    """

    node: QueryNodeType
    alias: AliasedClass[Any]
    """Alias the functions are built against."""
    functions: dict[QueryNodeType, Label[Any]] = dataclasses.field(default_factory=dict)
    selection_functions: set[QueryNodeType] = dataclasses.field(default_factory=set)
    """Function nodes the client selected."""

    @classmethod
    def create(cls, node: QueryNodeType, scope: AliasContext[Any]) -> Self:
        """Creates an empty spec for ``node``, with a new alias of its related model."""
        alias = aliased(scope.inspect(node).mapper)
        return cls(node=node, alias=alias)


def _filters_in_exists(tree: QueryNodeType, query_filter: Filter, scope: FilterScope) -> bool:
    fields = [node.value for node in tree.iter_breadth_first() if not node.is_root]
    if scope == "dml":
        return any(field.is_relation for field in fields) or any(
            isinstance(leaf, ExistsFilter) for leaf in query_filter.iter_leaves()
        )
    return scope == "query" and any(field.uselist and not field.is_computed for field in fields)


@dataclass
class QueryGraph(Generic[DeclarativeT]):
    """What a GraphQL query selects, filters and orders by, and the relations each part must join."""

    scope: AliasContext[DeclarativeT]
    selection_tree: QueryNodeType | None = None
    order_by: Sequence[OrderByDTO] = dataclasses.field(default_factory=list)
    distinct_on: list[EnumDTO] = dataclasses.field(default_factory=list)
    dto_filter: BooleanFilterDTO | None = None
    filter_scope: FilterScope = "query"
    """Statement the filter restricts; ``subquery`` is the EXISTS copy of the root, which joins every relation."""

    query_filter: Filter | None = dataclasses.field(init=False, default=None)
    exists_filter: BooleanFilterDTO | None = dataclasses.field(init=False, default=None)
    """Filter on relations, tested in an EXISTS subquery so that it neither joins nor repeats the root rows."""
    where_join_path: Sequence[QueryNodeType] = dataclasses.field(init=False, default=())
    """Relations inner-joined once for every predicate of ``query_filter``."""
    where_join_tree: QueryNodeType | None = dataclasses.field(init=False, default=None)
    """Relations the filter uses."""
    subquery_join_tree: QueryNodeType | None = dataclasses.field(init=False, default=None)
    """Relations the filter and the ordering use; joined inside the pagination subquery."""
    root_join_tree: QueryNodeType = dataclasses.field(init=False)
    """Relations the selection, the filter and the ordering use."""
    order_by_nodes: list[QueryNodeType] = dataclasses.field(init=False, default_factory=list)
    """Order-by leaves, in the order the client gave them."""

    def __post_init__(self) -> None:
        self.root_join_tree = self.resolved_selection_tree()
        if self.dto_filter is not None:
            self._split_filter(self.dto_filter)
        if self.where_join_tree is not None:
            self.subquery_join_tree = self.where_join_tree
            self.root_join_tree = merge_trees(self.root_join_tree, self.where_join_tree, match_on="value_equality")
        if self.order_by_tree:
            self.root_join_tree = merge_trees(self.root_join_tree, self.order_by_tree, match_on="value_equality")
            self.subquery_join_tree = (
                merge_trees(
                    self.subquery_join_tree,
                    self.order_by_tree,
                    match_on="value_equality",
                )
                if self.subquery_join_tree
                else self.order_by_tree
            )
            self.order_by_nodes = sorted(self.order_by_tree.leaves())

    def _split_filter(self, dto_filter: BooleanFilterDTO) -> None:
        """Moves to ``exists_filter`` the top-level AND branches that must be tested in an EXISTS subquery."""
        where_join_tree, query_filter = dto_filter.filters_tree()
        if not _filters_in_exists(where_join_tree, query_filter, self.filter_scope):
            self.where_join_tree, self.query_filter = where_join_tree, query_filter
            self.where_join_path = query_filter.join_path()
            return
        root_parts: list[BooleanFilterDTO] = []
        exists_parts: list[BooleanFilterDTO] = []
        for part in dto_filter.conjuncts():
            in_exists = _filters_in_exists(*part.filters_tree(), self.filter_scope)
            (exists_parts if in_exists else root_parts).append(part)
        if not root_parts:
            self.exists_filter = dto_filter
            return
        self.exists_filter = dto_filter.all_of(exists_parts)
        self.where_join_tree, self.query_filter = dto_filter.all_of(root_parts).filters_tree()
        self.where_join_path = self.query_filter.join_path()

    def resolved_selection_tree(self) -> QueryNodeType:
        """Returns the selection tree of the listed rows, or a tree of the primary keys when nothing is selected."""
        tree = self.selection_tree
        if tree and tree.graph_metadata.metadata.root_aggregations:
            tree = tree.find_child(lambda child: child.value.name == NODES_KEY) if tree else None
        if tree is None:
            tree = QueryNode.root_node(self.scope.model)
            for field in self.scope.id_field_definitions(self.scope.model):
                tree.insert_child(field)

        return tree

    @cached_property
    def order_by_tree(self) -> QueryNodeType | None:
        """Merges the order-by inputs into one tree whose leaves keep the order the client gave them."""
        merged_tree: QueryNodeType | None = None
        max_order: int = 0
        for order_by_dto in self.order_by:
            if not order_by_dto.has_order():
                continue
            tree = order_by_dto.tree()
            orders: list[int] = []
            for leaf in sorted(tree.leaves(iteration_mode="breadth_first")):
                leaf.insert_order += max_order
                orders.append(leaf.insert_order)
            merged_tree = tree if merged_tree is None else merge_trees(merged_tree, tree, match_on="value_equality")
            max_order = max(orders) + 1
        return merged_tree

    @cached_property
    def selects_to_many_relation(self) -> bool:
        """Whether a selected relation can repeat the root rows."""
        return any(
            node.value.uselist and not node.value.is_computed
            for node in self.resolved_selection_tree().iter_breadth_first()
            if not node.is_root
        )

    @cached_property
    def filter_relation_nodes(self) -> list[QueryNodeType]:
        """Relations the filter joins."""
        if self.where_join_tree is None:
            return []
        return [
            node
            for node in self.where_join_tree.iter_breadth_first()
            if not node.is_root and node.value.is_relation and not node.value.is_computed
        ]

    def root_aggregation_tree(self) -> QueryNodeType | None:
        if self.selection_tree:
            return self.selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        return None


@dataclass
class Conjunction:
    """Filter predicates with the joins they need."""

    expressions: list[ColumnElement[bool]] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)

    def has_many_predicates(self) -> bool:
        """Whether there are several predicates, counting those inside a single ``and_`` or ``or_``."""
        if not self.expressions:
            return False
        return len(self.expressions) > 1 or (
            isinstance(self.expressions[0], BooleanClauseList) and len(self.expressions[0]) > 1
        )


@dataclass
class Where:
    """WHERE predicates with every join they need."""

    conjunction: Conjunction = dataclasses.field(default_factory=Conjunction)
    joins: list[Join] = dataclasses.field(default_factory=list)

    @property
    def expressions(self) -> list[ColumnElement[bool]]:
        return self.conjunction.expressions

    def clear_expressions(self) -> None:
        self.conjunction.expressions.clear()

    @classmethod
    def from_expressions(cls, *expressions: ColumnElement[bool]) -> Self:
        """Creates a WHERE clause from predicates needing no join."""
        return cls(Conjunction(list(expressions)))


@dataclass
class OrderBy:
    """ORDER BY columns with the joins they need."""

    db_features: DatabaseFeatures
    columns: list[OrderBySpec] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)

    def _order_by(self, column: SQLColumnExpression[Any], order_by: OrderByEnum) -> list[UnaryExpression[Any]]:
        """Builds the ORDER BY expressions of one column.

        On databases without ``NULLS FIRST``/``NULLS LAST``, null placement is done by ordering on ``column IS NULL``
        first.
        """
        expressions: list[UnaryExpression[Any]] = []
        if order_by is OrderByEnum.ASC:
            expressions.append(column.asc())
        elif order_by is OrderByEnum.DESC:
            expressions.append(column.desc())
        elif order_by is OrderByEnum.ASC_NULLS_FIRST and self.db_features.supports_null_ordering:
            expressions.append(column.asc().nulls_first())
        elif order_by is OrderByEnum.ASC_NULLS_FIRST:
            expressions.extend([(column.is_(null())).desc(), column.asc()])
        elif order_by is OrderByEnum.ASC_NULLS_LAST and self.db_features.supports_null_ordering:
            expressions.append(column.asc().nulls_last())
        elif order_by is OrderByEnum.ASC_NULLS_LAST:
            expressions.extend([(column.is_(null())).asc(), column.asc()])
        elif order_by is OrderByEnum.DESC_NULLS_FIRST and self.db_features.supports_null_ordering:
            expressions.append(column.desc().nulls_first())
        elif order_by is OrderByEnum.DESC_NULLS_FIRST:
            expressions.extend([(column.is_(null())).desc(), column.desc()])
        elif order_by is OrderByEnum.DESC_NULLS_LAST and self.db_features.supports_null_ordering:
            expressions.append(column.desc().nulls_last())
        elif order_by is OrderByEnum.DESC_NULLS_LAST:
            expressions.extend([(column.is_(null())).asc(), column.desc()])
        return expressions

    @property
    def expressions(self) -> list[UnaryExpression[Any]]:
        """The ORDER BY expressions of all columns."""
        expressions: list[UnaryExpression[Any]] = []
        for column, order_by in self.columns:
            expressions.extend(self._order_by(column, order_by))
        return expressions


@dataclass
class DistinctOn:
    """The DISTINCT ON columns of a query; false when the query has none."""

    query_graph: QueryGraph[Any]

    @property
    def _distinct_on_fields(self) -> list[GraphQLFieldDefinition]:
        return [enum.field_definition for enum in self.query_graph.distinct_on]

    @property
    def expressions(self) -> list[QueryableAttribute[Any]]:
        """The DISTINCT ON columns, read from the root alias.

        Raises:
            TranspilingError: If the DISTINCT ON fields are not the first ORDER BY fields, in the same order.
        """
        for i, distinct_field in enumerate(self._distinct_on_fields):
            if i > len(self.query_graph.order_by_nodes) - 1:
                break
            if self.query_graph.order_by_nodes[i].value.model_field is distinct_field.model_field:
                continue
            msg = "Distinct on fields must match the leftmost order by fields"
            raise TranspilingError(msg)
        return [
            field.model_field.adapt_to_entity(inspect(self.query_graph.scope.root_alias))
            for field in self._distinct_on_fields
        ]

    def __bool__(self) -> bool:
        return bool(self.expressions)


@dataclass
class HookApplier:
    """Runs the query hooks registered on each query node."""

    scope: AliasContext[Any]
    hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )

    def has_hooks(self, node: QueryNodeType) -> bool:
        return bool(self.hooks.get(node))

    def without(self, nodes: Sequence[QueryNodeType]) -> HookApplier:
        """Returns a copy that runs no hook of ``nodes``."""
        return HookApplier(
            self.scope, defaultdict(list, {node: hooks for node, hooks in self.hooks.items() if node not in nodes})
        )

    def apply(
        self,
        statement: Select[tuple[DeclarativeT]],
        node: QueryNodeType,
        alias: AliasedClass[Any],
        loading_mode: ColumnLoadingMode,
        *,
        in_subquery: bool = False,
        export_order_by: bool = False,
    ) -> tuple[Select[tuple[DeclarativeT]], list[_AbstractLoad]]:
        """Runs every hook of ``node`` on ``statement`` and returns the loader options they add.

        Each hook edits the statement, then adds its columns and, outside a subquery, its relationship loads.
        With ``export_order_by``, the ORDER BY the hooks add is dropped and the columns it reads are selected instead.
        """
        options: list[_AbstractLoad] = []
        order_by = statement._order_by_clauses  # noqa: SLF001
        for hook in self.hooks[node]:
            statement = hook.apply_hook(statement, alias)
            statement, column_options = hook.load_columns(statement, alias, loading_mode)
            options.extend(column_options)
            if not in_subquery:
                options.extend(hook.load_relationships(self.scope.alias_from_relation_node(node, "target")))
        if export_order_by:
            hook_order_by = statement._order_by_clauses[len(order_by) :]  # noqa: SLF001
            statement = add_missing_columns(statement.order_by(None).order_by(*order_by), _columns_of(hook_order_by))
        return statement, options

    def order_by(self, node: QueryNodeType, alias: AliasedClass[Any]) -> tuple[UnaryExpression[Any], ...]:
        """Returns the ORDER BY the hooks of ``node`` add, built against ``alias``."""
        statement = self.apply_statement_hooks(select(alias), node, alias)
        return tuple(
            clause if isinstance(clause, UnaryExpression) else clause.asc()
            for clause in statement._order_by_clauses  # noqa: SLF001
        )

    def collect_load_options(
        self, node: QueryNodeType, alias: AliasedClass[Any], in_subquery: bool = False
    ) -> list[_AbstractLoad]:
        """Returns the column and relationship loader options of the hooks of ``node``, without editing a statement.

        Relationship loads are left out in a subquery.
        """
        options: list[_AbstractLoad] = []
        for hook in self.hooks[node]:
            options.extend(hook.column_load_options(alias))
            if not in_subquery:
                options.extend(hook.load_relationships(self.scope.alias_from_relation_node(node, "target")))
        return options

    def apply_statement_hooks(
        self, statement: Select[tuple[DeclarativeT]], node: QueryNodeType, alias: AliasedClass[Any]
    ) -> Select[tuple[DeclarativeT]]:
        """Runs ``apply_hook`` of every hook of ``node`` on ``statement``, without loading columns or relations."""
        for hook in self.hooks[node]:
            statement = hook.apply_hook(statement, alias)
        return statement


def _columns_of(clauses: Iterable[ColumnElement[Any]]) -> list[ColumnElement[Any]]:
    """Returns the table columns ``clauses`` read, once each, in order of appearance."""
    columns: list[ColumnElement[Any]] = []
    for clause in clauses:
        for element in iterate(clause):
            if isinstance(element, ColumnClause) and not any(same_column(element, column) for column in columns):
                columns.append(element)
    return columns
