from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy import (
    CTE,
    BooleanClauseList,
    Label,
    Lateral,
    Select,
    UnaryExpression,
    inspect,
    null,
)
from sqlalchemy.orm import (
    QueryableAttribute,
    RelationshipDirection,
    RelationshipProperty,
    aliased,
)
from sqlalchemy.orm.util import AliasedClass
from typing_extensions import Self

from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.dto.strawberry import (
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)
from strawchemy.exceptions import TranspilingError
from strawchemy.repository.typing import DeclarativeT, OrderBySpec
from strawchemy.utils.graph import merge_trees

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql._typing import _OnClauseArgument
    from sqlalchemy.sql.selectable import NamedFromClause

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.transpiler import ColumnLoadingMode, QueryHook
    from strawchemy.transpiler._aliasing import AliasContext
    from strawchemy.typing import QueryNodeType

__all__ = ("AggregationJoin", "AggregationSpec", "Conjunction", "DistinctOn", "Join", "OrderBy", "QueryGraph", "Where")


@dataclass
class Join:
    """Represents a join to be applied to a SQLAlchemy query.

    This class encapsulates information about a join, including the target entity,
    the corresponding query node, join conditions, and ordering information.

    Attributes:
        target: The SQLAlchemy entity, CTE, or aliased class to join with.
        node: The query node type representing this join in the query graph.
        onclause: Optional custom ON clause for the join.
        is_outer: Whether this join is an outer join (LEFT OUTER JOIN).
        order_nodes: List of query nodes that define the order within this join,
            particularly relevant for ordered relationships.
    """

    target: QueryableAttribute[Any] | NamedFromClause | AliasedClass[Any] | CTE | Lateral
    node: QueryNodeType
    onclause: _OnClauseArgument | None = None
    is_outer: bool = False
    order_nodes: list[QueryNodeType] = dataclasses.field(default_factory=list)

    @property
    def _relationship(self) -> RelationshipProperty[Any]:
        """The SQLAlchemy RelationshipProperty associated with this join node."""
        return cast("RelationshipProperty[Any]", self.node.value.model_field.property)

    @property
    def selectable(self) -> NamedFromClause:
        """The SQLAlchemy selectable (table, CTE, etc.) for this join target."""
        if isinstance(self.target, AliasedClass):
            return cast("NamedFromClause", inspect(self.target).selectable)
        return cast("NamedFromClause", self.target)

    @property
    def order(self) -> int:
        """The order (depth level) of this join in the query graph."""
        return self.node.level

    @property
    def to_many(self) -> bool:
        """Whether this join represents a to-many relationship."""
        return self._relationship.direction in {
            RelationshipDirection.MANYTOMANY,
            RelationshipDirection.ONETOMANY,
        }

    def __gt__(self, other: Self) -> bool:
        """Compares this join with another based on their order (depth)."""
        return self.order > other.order

    def __lt__(self, other: Self) -> bool:
        """Compares this join with another based on their order (depth)."""
        return self.order < other.order

    def __le__(self, other: Self) -> bool:
        """Compares this join with another based on their order (depth)."""
        return self.order <= other.order

    def __ge__(self, other: Self) -> bool:
        """Compares this join with another based on their order (depth)."""
        return self.order >= other.order


@dataclass(kw_only=True)
class AggregationJoin(Join):
    """Marker join distinguishing aggregation joins from regular relation joins.

    This class extends `Join` with no extra state. It exists solely so aggregation
    joins can be discriminated via ``isinstance`` (e.g. when excluding them from
    relation ordering).
    """


@dataclass
class AggregationSpec:
    """Describes a single aggregation join to build once with all of its function columns.

    A spec is accumulated across the filter, order-by and selection passes for one
    ``aggregation_node`` (the ``is_aggregate`` node). Each distinct function expression
    is keyed by its ``function_node`` so the same function referenced by several sources
    resolves to a single built column.

    Attributes:
        node: The aggregation node this spec builds a join for.
        alias: The aliased target class the function expressions are adapted to.
        functions: Labeled function expressions keyed by their function node.
    """

    node: QueryNodeType
    alias: AliasedClass[Any]
    functions: dict[QueryNodeType, Label[Any]] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(cls, node: QueryNodeType, scope: AliasContext[Any]) -> Self:
        """Creates a spec for an aggregation node with a fresh adaptation alias.

        Args:
            node: The aggregation node to build a spec for.
            scope: The query scope used to resolve the node's mapper.

        Returns:
            A new spec whose ``alias`` is an aliased target class the function
            expressions are adapted to.
        """
        alias = cast("AliasedClass[Any]", aliased(scope.inspect(node).mapper))
        return cls(node=node, alias=alias)


@dataclass
class QueryGraph(Generic[DeclarativeT]):
    """Represents the structure and components of a GraphQL query to be translated to SQLAlchemy.

    This class holds information about the selected fields (selection_tree),
    ordering, distinct clauses, and filters. It processes these components to build
    various join trees (root, where, subquery) necessary for constructing the
    final SQLAlchemy query.

    Attributes:
        scope: The AliasContext, providing context about the root model and database features.
        selection_tree: The root node of the GraphQL query's selection set.
        order_by: A sequence of OrderByDTOs specifying how the results should be ordered.
        distinct_on: A list of EnumDTOs specifying fields for a DISTINCT ON clause.
        dto_filter: A BooleanFilterDTO representing the filtering conditions.
        query_filter: The processed Filter object derived from dto_filter.
        where_join_tree: The join tree required by the WHERE clause filters.
        subquery_join_tree: The join tree required by subqueries (often for aggregations or complex filters).
        root_join_tree: The main join tree representing all required joins for the query.
        order_by_nodes: A list of query nodes involved in the ORDER BY clause.
    """

    scope: AliasContext[DeclarativeT]
    selection_tree: QueryNodeType | None = None
    order_by: Sequence[OrderByDTO] = dataclasses.field(default_factory=list)
    distinct_on: list[EnumDTO] = dataclasses.field(default_factory=list)
    dto_filter: BooleanFilterDTO | None = None

    query_filter: Filter | None = dataclasses.field(init=False, default=None)
    where_join_tree: QueryNodeType | None = dataclasses.field(init=False, default=None)
    subquery_join_tree: QueryNodeType | None = dataclasses.field(init=False, default=None)
    root_join_tree: QueryNodeType = dataclasses.field(init=False)
    order_by_nodes: list[QueryNodeType] = dataclasses.field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Initializes various join trees based on the selection, filters, and ordering.

        This method constructs the `root_join_tree`, `where_join_tree`, and
        `subquery_join_tree` by merging trees derived from the selection set,
        filters, order by clauses, and distinct on clauses.
        """
        self.root_join_tree = self.resolved_selection_tree()
        if self.dto_filter is not None:
            self.where_join_tree, self.query_filter = self.dto_filter.filters_tree()
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

    def resolved_selection_tree(self) -> QueryNodeType:
        """Resolves the selection tree by adding root aggregations and selection functions.

        This method processes the selection tree to include root aggregations and
        selection functions, ensuring that all necessary nodes are included for
        the query.

        Returns:
            The resolved selection tree.
        """
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
        """Creates a query node tree from a list of order by DTOs.

        Args:
            dtos: List of order by DTOs to create the tree from.

        Returns:
            A query node tree representing the order by clauses, or None if no DTOs provided.
        """
        merged_tree: QueryNodeType | None = None
        max_order: int = 0
        for order_by_dto in self.order_by:
            tree = order_by_dto.tree()
            orders: list[int] = []
            for leaf in sorted(tree.leaves(iteration_mode="breadth_first")):
                leaf.insert_order += max_order
                orders.append(leaf.insert_order)
            merged_tree = tree if merged_tree is None else merge_trees(merged_tree, tree, match_on="value_equality")
            max_order = max(orders) + 1
        return merged_tree

    def root_aggregation_tree(self) -> QueryNodeType | None:
        if self.selection_tree:
            return self.selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        return None


@dataclass
class Conjunction:
    """Represents a group of SQLAlchemy filter expressions and their associated joins.

    A conjunction typically corresponds to a set of conditions that are ANDed
    together in a WHERE clause. It also tracks the common join path required
    by these expressions to ensure correct query construction.

    Attributes:
        expressions: A list of SQLAlchemy boolean column elements representing
            the filter conditions.
        joins: A list of `Join` objects required to evaluate the expressions.
        common_join_path: A list of `QueryNodeType` objects representing the
            deepest common path in the query graph shared by all expressions
            in this conjunction. This helps in optimizing join structures.
    """

    expressions: list[ColumnElement[bool]] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)
    common_join_path: list[QueryNodeType] = dataclasses.field(default_factory=list)

    def has_many_predicates(self) -> bool:
        """Checks if the conjunction contains multiple filter predicates.

        This is true if there's more than one expression, or if the single
        expression is itself a `BooleanClauseList` (e.g., an `and_` or `or_`)
        containing multiple sub-expressions.

        Returns:
            True if there are multiple predicates, False otherwise.
        """
        if not self.expressions:
            return False
        return len(self.expressions) > 1 or (
            isinstance(self.expressions[0], BooleanClauseList) and len(self.expressions[0]) > 1
        )


@dataclass
class Where:
    """Represents the WHERE clause of a SQLAlchemy query.

    This class encapsulates the filter conditions (as a `Conjunction`) and
    any additional joins specifically required by these conditions.

    Attributes:
        conjunction: A `Conjunction` object holding the filter expressions
            and their associated joins.
        joins: A list of `Join` objects that are specific to the WHERE clause,
            beyond those already in the conjunction.
    """

    conjunction: Conjunction = dataclasses.field(default_factory=Conjunction)
    joins: list[Join] = dataclasses.field(default_factory=list)

    @property
    def expressions(self) -> list[ColumnElement[bool]]:
        """The list of SQLAlchemy boolean filter expressions."""
        return self.conjunction.expressions

    def clear_expressions(self) -> None:
        """Clears all filter expressions from the WHERE clause."""
        self.conjunction.expressions.clear()

    @classmethod
    def from_expressions(cls, *expressions: ColumnElement[bool]) -> Self:
        """Creates a `Where` clause instance from one or more SQLAlchemy expressions.

        Args:
            *expressions: SQLAlchemy boolean column elements to be used as
                filter conditions.

        Returns:
            A new `Where` instance populated with the given expressions.
        """
        return cls(Conjunction(list(expressions)))


@dataclass
class OrderBy:
    """Manages the ORDER BY clause components for a SQLAlchemy query.

    This class stores the columns to order by, their respective ordering directions
    (ASC, DESC, with NULLS FIRST/LAST handling), and any joins required to access
    these columns. It also considers database-specific features for NULL ordering.

    Attributes:
        db_features: An instance of `DatabaseFeatures` providing information about
            the capabilities of the target database (e.g., support for NULLS FIRST/LAST).
        columns: A list of tuples, where each tuple contains a SQLAlchemy column expression
            and an `OrderByEnum` value specifying the ordering for that column.
        joins: A list of `Join` objects required to access the columns specified in the
            ORDER BY clause.
    """

    db_features: DatabaseFeatures
    columns: list[OrderBySpec] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)

    def _order_by(self, column: SQLColumnExpression[Any], order_by: OrderByEnum) -> list[UnaryExpression[Any]]:
        """Creates an order by expression for a given node and attribute.

        Args:
            column: The order by enum value (ASC, DESC, etc.).
            order_by: The column or attribute to order by.

        Returns:
            A unary expression representing the order by clause.
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
        """Generates a list of SQLAlchemy UnaryExpression objects for the ORDER BY clause.

        This method iterates through the `columns` and uses the `_order_by` method
        to convert each column and its ordering specification into the appropriate
        SQLAlchemy expression (e.g., `column.asc()`, `column.desc().nulls_first()`).

        Returns:
            A list of SQLAlchemy UnaryExpression objects ready to be applied to a query.
        """
        expressions: list[UnaryExpression[Any]] = []
        for column, order_by in self.columns:
            expressions.extend(self._order_by(column, order_by))
        return expressions


@dataclass
class DistinctOn:
    """Manages the DISTINCT ON clause for a SQLAlchemy query.

    This class is responsible for generating the expressions for a `DISTINCT ON`
    clause. It ensures that the fields used in `DISTINCT ON` are compatible
    with the database and align with the initial fields of any `ORDER BY` clause,
    which is a requirement for `DISTINCT ON` in PostgreSQL.

    Attributes:
        query_graph: The `QueryGraph` instance providing context about the overall
            query structure, including selected fields and ordering, which is necessary
            to validate and construct the `DISTINCT ON` clause.
    """

    query_graph: QueryGraph[Any]

    @property
    def _distinct_on_fields(self) -> list[GraphQLFieldDefinition]:
        """Extracts the fields relevant for the DISTINCT ON clause.

        These fields are derived from the `distinct_on` attribute of the `query_graph`.

        Returns:
            A list of `GraphQLFieldDefinition` instances for the DISTINCT ON clause.
        """
        return [enum.field_definition for enum in self.query_graph.distinct_on]

    @property
    def expressions(self) -> list[QueryableAttribute[Any]]:
        """Creates DISTINCT ON expressions from the fields specified in the query graph.

        This method retrieves the fields intended for `DISTINCT ON` using
        `_distinct_on_fields`. It then validates these fields against the
        `order_by_nodes` from the `query_graph`. For `DISTINCT ON` to be valid
        (especially in PostgreSQL), the expressions in `DISTINCT ON` must match
        the leftmost expressions in the `ORDER BY` clause.

        Returns:
            A list of SQLAlchemy `QueryableAttribute` objects that can be used
            in a `SELECT.distinct(*attributes)` call.

        Raises:
            TranspilingError: If the `DISTINCT ON` fields do not correspond to the
                leftmost `ORDER BY` fields, or if `ORDER BY` is not specified when
                `DISTINCT ON` is used (and the database requires it).
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
        """Checks if any DISTINCT ON fields are specified in the query graph.

        Returns:
            True if `query_graph.distinct_on` is populated, False otherwise.
        """
        return bool(self.expressions)


@dataclass
class HookApplier:
    """Manages and applies query hooks to SQLAlchemy SELECT statements.

    This class is responsible for invoking registered `QueryHook` instances
    at appropriate points during the construction of a SQLAlchemy query.
    Hooks can modify the statement, for example, by adding columns, applying
    transformations, or changing loader options, based on the current
    `QueryNodeType` being processed.

    Attributes:
        scope: The `AliasContext` providing context (e.g., root model, database
            features) that might be relevant for hook execution.
        hooks: A `defaultdict` mapping `QueryNodeType` instances to a list of
            `QueryHook` objects. This allows multiple hooks to be registered
            and applied for the same node type.
    """

    scope: AliasContext[Any]
    hooks: defaultdict[QueryNodeType, list[QueryHook[Any]]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )

    def apply(
        self,
        statement: Select[tuple[DeclarativeT]],
        node: QueryNodeType,
        alias: AliasedClass[Any],
        loading_mode: ColumnLoadingMode,
        in_subquery: bool = False,
    ) -> tuple[Select[tuple[DeclarativeT]], list[_AbstractLoad]]:
        """Applies registered hooks for a given node to the SELECT statement.

        This method iterates through all `QueryHook` instances registered for the
        specified `node`. For each hook, it applies transformations to the
        `statement` and collects SQLAlchemy loader options.

        The application process for each hook involves:
        1. `hook.apply_hook(statement, alias)`: For general statement modifications.
        2. `hook.load_columns(statement, alias, loading_mode)`: For adding columns
           or defining column loading strategies. Loader options are collected.
        3. `hook.load_relationships(...)`: If `in_subquery` is False, this allows
           hooks to define relationship loading strategies. The target alias for
           the relationship is resolved using `self.scope.alias_from_relation_node`.
           Loader options are collected.

        Args:
            statement: The SQLAlchemy `Select` statement to modify.
            node: The `QueryNodeType` identifying which set of hooks to apply.
            alias: The `AliasedClass` representing the current ORM context for the hooks.
            loading_mode: Specifies the general strategy for loading columns,
                which hooks can customize.
            in_subquery: If True, relationship loading hooks are skipped, as they
                are typically not applicable within subqueries. Defaults to False.

        Returns:
            A tuple containing the modified `Select` statement and a list of
            SQLAlchemy loader options (`_AbstractLoad`) accumulated from the hooks.
        """
        options: list[_AbstractLoad] = []
        for hook in self.hooks[node]:
            statement = hook.apply_hook(statement, alias)
            statement, column_options = hook.load_columns(statement, alias, loading_mode)
            options.extend(column_options)
            if not in_subquery:
                options.extend(hook.load_relationships(self.scope.alias_from_relation_node(node, "target")))
        return statement, options

    def collect_load_options(
        self, node: QueryNodeType, alias: AliasedClass[Any], in_subquery: bool = False
    ) -> list[_AbstractLoad]:
        """Collects loader options (undefer columns + relationships) from a node's hooks.

        Excludes ``apply_hook`` statement mutations — those are applied separately.

        Args:
            node: The node whose hooks contribute loader options.
            alias: The aliased entity passed to the hooks.
            in_subquery: When True, relationship loads are skipped.

        Returns:
            The accumulated loader options.
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
        """Applies a node's hooks' ``apply_hook`` statement mutations only.

        Args:
            statement: The statement to mutate.
            node: The node whose hooks apply.
            alias: The aliased entity passed to the hooks.

        Returns:
            The mutated statement.
        """
        for hook in self.hooks[node]:
            statement = hook.apply_hook(statement, alias)
        return statement
