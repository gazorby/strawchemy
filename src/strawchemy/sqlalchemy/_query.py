from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, cast

from sqlalchemy.orm import (
    QueryableAttribute,
    RelationshipDirection,
    RelationshipProperty,
    aliased,
    class_mapper,
    raiseload,
)
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql.elements import NamedColumn
from typing_extensions import Self

from sqlalchemy import (
    CTE,
    AliasedReturnsRows,
    BooleanClauseList,
    Label,
    Lateral,
    Select,
    Subquery,
    UnaryExpression,
    func,
    inspect,
    null,
    select,
)
from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.graph import merge_trees
from strawchemy.sqlalchemy.exceptions import TranspilingError
from strawchemy.sqlalchemy.typing import DeclarativeT, OrderBySpec
from strawchemy.strawberry.dto import (
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.sql import ColumnElement, SQLColumnExpression
    from sqlalchemy.sql._typing import _OnClauseArgument
    from sqlalchemy.sql.selectable import NamedFromClause

    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.sqlalchemy._scope import QueryScope
    from strawchemy.sqlalchemy.hook import ColumnLoadingMode, QueryHook
    from strawchemy.strawberry.typing import QueryNodeType

__all__ = ("AggregationJoin", "Conjunction", "DistinctOn", "Join", "OrderBy", "QueryGraph", "Where")


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

    def __init__(
        self,
        target: QueryableAttribute[Any] | NamedFromClause | AliasedClass[Any],
        node: QueryNodeType,
        onclause: _OnClauseArgument | None = None,
        is_outer: bool = False,
        order_nodes: list[QueryNodeType] | None = None,
    ) -> None:
        self.target = target
        self.node = node
        self.onclause = onclause
        self.is_outer = is_outer
        self.order_nodes = order_nodes if order_nodes is not None else []

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
    def name(self) -> str:
        """The name of the selectable for this join."""
        return self.selectable.name

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


class AggregationJoin(Join):
    """Represents a join specifically for aggregation purposes, often involving a subquery.

    This class extends `Join` and is used when aggregations (e.g., counts, sums)
    need to be performed on related entities. It manages a subquery that computes
    these aggregations and ensures that columns in the subquery have unique names.

    Attributes:
        subquery_alias: An aliased class representing the subquery used for aggregation.
        _column_names: Internal tracking of column names within the subquery to ensure uniqueness.
    """

    def __init__(
        self,
        target: QueryableAttribute[Any] | NamedFromClause | AliasedClass[Any],
        node: QueryNodeType,
        subquery_alias: AliasedClass[Any],
        onclause: _OnClauseArgument | None = None,
        is_outer: bool = False,
        order_nodes: list[QueryNodeType] | None = None,
    ) -> None:
        super().__init__(target, node, onclause, is_outer, order_nodes)
        self.subquery_alias = subquery_alias
        self._column_names: defaultdict[str, int] = defaultdict(int)

        # Initialize the _column_names mapping from the subquery's selected columns
        for column in self._inner_select.selected_columns:
            if isinstance(column, NamedColumn):
                self._column_names[column.name] = 1

    @property
    def _inner_select(self) -> Select[Any]:
        """The inner SELECT statement of the subquery used for aggregation."""
        if isinstance(self.selectable, CTE):
            return cast("Select[Any]", self.selectable.element)
        self_join = cast("AliasedReturnsRows", self.selectable)
        return cast("Select[Any]", cast("Subquery", self_join.element).element)

    def _existing_function_column(self, new_column: ColumnElement[Any]) -> ColumnElement[Any] | None:
        """Checks if an equivalent column (typically a function call) already exists in the subquery.

        This is used to avoid adding duplicate aggregate functions to the subquery.

        Args:
            new_column: The new column (potentially a function) to check.

        Returns:
            The existing column if a match is found, otherwise None.
        """
        for column in self._inner_select.selected_columns:
            base_columns = column.base_columns
            new_base_columns = new_column.base_columns
            if len(base_columns) != len(new_base_columns):
                continue
            for first, other in zip(base_columns, new_base_columns, strict=False):
                if not first.compare(other):
                    break
            else:
                return column
        return None

    def _ensure_unique_name(self, column: ColumnElement[Any]) -> ColumnElement[Any]:
        """Ensures that the given column has a unique name within the subquery.

        If a column with the same name already exists, it appends a suffix (e.g., '_1').

        Args:
            column: The column to ensure has a unique name.

        Returns:
            The column, possibly relabeled to ensure uniqueness.
        """
        if not isinstance(column, NamedColumn):
            return column
        if self._column_names[column.name]:
            name = f"{column.name}_{self._column_names[column.name]}"
            self._column_names[column.name] += 1
        else:
            name = column.name
        return column.label(name)

    def add_column_to_subquery(self, column: ColumnElement[Any]) -> None:
        """Adds a new column to the aggregation subquery.

        The column name is made unique before adding.
        The subquery (CTE or Lateral) is then rebuilt with the new column.

        Args:
            column: The column to add to the subquery.
        """
        new_sub_select = self._inner_select.add_columns(self._ensure_unique_name(column))

        if isinstance(self.selectable, Lateral):
            new_sub_select = new_sub_select.lateral(self.name)
        else:
            new_sub_select = new_sub_select.cte(self.name)

        if isinstance(self.target, AliasedClass):
            inspect(self.target).selectable = new_sub_select
        else:
            self.target = new_sub_select

    def upsert_column_to_subquery(self, column: ColumnElement[Any]) -> tuple[ColumnElement[Any], bool]:
        """Adds a column to the subquery if an equivalent one doesn't already exist.

        If an equivalent column (e.g., the same aggregate function on the same base column)
        is already present, it returns the existing column. Otherwise, it adds the new
        column and returns it.

        Args:
            column: The column to potentially add to the subquery.

        Returns:
            A tuple containing the column (either existing or newly added) and a boolean
            indicating whether the column was newly added (True) or already existed (False).
        """
        if (existing := self._existing_function_column(column)) is not None:
            return existing, False
        self.add_column_to_subquery(column)
        return column, True


@dataclass
class QueryGraph(Generic[DeclarativeT]):
    """Represents the structure and components of a GraphQL query to be translated to SQLAlchemy.

    This class holds information about the selected fields (selection_tree),
    ordering, distinct clauses, and filters. It processes these components to build
    various join trees (root, where, subquery) necessary for constructing the
    final SQLAlchemy query.

    Attributes:
        scope: The QueryScope, providing context about the root model and database features.
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

    scope: QueryScope[DeclarativeT]
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

        for node in tree.leaves(iteration_mode="breadth_first"):
            if node.value.is_function:
                self.scope.selection_function_nodes.add(node)

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
class Query:
    """Encapsulates all components required to build a SQLAlchemy query.

    This class acts as a container for various parts of a query, such as
    database-specific features, distinct clauses, joins, filtering conditions (WHERE),
    ordering (ORDER BY), root-level aggregation functions, and pagination (limit/offset).
    It provides a structured way to assemble these components before generating
    the final SQLAlchemy `Select` statement.

    Attributes:
        db_features: An instance of `DatabaseFeatures` providing information about
            the capabilities of the target database.
        distinct_on: A `DistinctOn` object managing the expressions for a
            `DISTINCT ON` clause.
        joins: A list of `Join` objects representing the joins to be applied.
        where: An optional `Where` object containing the filter conditions.
        order_by: An optional `OrderBy` object specifying the sorting criteria.
        root_aggregation_functions: A list of SQLAlchemy `Label` objects for
            aggregations performed at the root level of the query (e.g., total counts).
        limit: An optional integer specifying the maximum number of rows to return.
        offset: An optional integer specifying the number of rows to skip before
            starting to return rows.
        use_distinct_on: A boolean flag indicating whether `DISTINCT ON` should be
            actively applied. This can depend on database support and query structure.
    """

    db_features: DatabaseFeatures
    distinct_on: DistinctOn
    joins: list[Join] = dataclasses.field(default_factory=list)
    where: Where | None = None
    order_by: OrderBy | None = None
    root_aggregation_functions: list[Label[Any]] = dataclasses.field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    use_distinct_on: bool = False

    def _distinct_on(self, statement: Select[Any], order_by_expressions: list[UnaryExpression[Any]]) -> Select[Any]:
        """Applies DISTINCT ON expressions to the SELECT statement.

        If `self.use_distinct_on` is True, this method modifies the given `statement`
        to include `DISTINCT ON` behavior. It retrieves distinct expressions from
        `self.distinct_on`.

        Crucially, for `DISTINCT ON` to work correctly (especially in PostgreSQL),
        the columns in the `ORDER BY` clause must be available in the `SELECT` list
        if they are part of the `DISTINCT ON` criteria or if `DISTINCT ON` is used
        at all with an `ORDER BY`. This method ensures that any such necessary columns
        from `order_by_expressions` are added to the statement's selected columns
        before applying `.distinct()`.

        Args:
            statement: The SQLAlchemy `Select` statement to modify.
            order_by_expressions: A list of `UnaryExpression` objects representing
                the `ORDER BY` clause, used to ensure necessary columns are selected.

        Returns:
            The modified `Select` statement, potentially with added columns and
            a `.distinct()` clause applied.
        """
        distinct_expressions = self.distinct_on.expressions if self.distinct_on else []

        if self.use_distinct_on:
            # Add ORDER BY columns not present in the SELECT clause
            statement = statement.add_columns(
                *[
                    expression.element
                    for expression in order_by_expressions
                    if not any(elem.compare(expression.element) for elem in statement.selected_columns)
                ]
            )
            statement = statement.distinct(*distinct_expressions)
        return statement

    @property
    def joins_have_many(self) -> bool:
        """Checks if any of the configured joins are to-many relationships.

        Returns:
            True if at least one join in `self.joins` has its `to_many` attribute
            set to True, indicating a join across a one-to-many or many-to-many
            relationship. False otherwise.
        """
        return next((True for join in self.joins if join.to_many), False)

    def statement(self, base_statement: Select[tuple[DeclarativeT]]) -> Select[tuple[DeclarativeT]]:
        """Constructs the final SQLAlchemy Select statement from the query components.

        This method takes a base SELECT statement (usually selecting from the root
        entity) and applies all configured query parts in a specific order:
        1. Joins (sorted by their defined order).
        2. WHERE clause conditions.
        3. ORDER BY clauses.
        4. DISTINCT ON clauses (if applicable, potentially modifying selected columns).
        5. LIMIT and OFFSET for pagination.
        6. Root-level aggregation functions are added to the selected columns.

        Args:
            base_statement: The initial SQLAlchemy `Select` object, typically selecting
                from the primary model or its alias.

        Returns:
            The fully constructed SQLAlchemy `Select` statement, incorporating all
            joins, filters, ordering, pagination, and aggregations.
        """
        sorted_joins = sorted(self.joins)
        distinct_expressions = self.distinct_on.expressions if self.distinct_on else []
        order_by_expressions = self.order_by.expressions if self.order_by else []

        for join in sorted_joins:
            base_statement = base_statement.join(join.target, onclause=join.onclause, isouter=join.is_outer)  # pyright: ignore[reportArgumentType]
        if self.where and self.where.expressions:
            base_statement = base_statement.where(*self.where.expressions)
        if order_by_expressions:
            base_statement = base_statement.order_by(*order_by_expressions)
        if distinct_expressions:
            base_statement = self._distinct_on(base_statement, order_by_expressions)
        if self.limit is not None:
            base_statement = base_statement.limit(self.limit)
        if self.offset is not None:
            base_statement = base_statement.offset(self.offset)

        return base_statement.add_columns(*self.root_aggregation_functions)


@dataclass
class SubqueryBuilder(Generic[DeclarativeT]):
    """Builds and manages aliased subqueries, often for DISTINCT ON emulation.

    This utility class is responsible for constructing aliased subqueries,
    particularly useful for emulating `DISTINCT ON` behavior with window functions
    (e.g., `ROW_NUMBER()`). It handles creating an alias for the target model,
    generating unique names for helper columns (like a rank column), and defining
    conditions based on these columns.

    Attributes:
        scope: The `QueryScope` providing context for the model being queried.
        hook_applier: A `HookApplier` instance for applying query hooks.
        db_features: `DatabaseFeatures` for database-specific logic.
        alias: An `AliasedClass` for `scope.model`, initialized in `__post_init__`.
    """

    scope: QueryScope[Any]
    hook_applier: HookApplier
    db_features: DatabaseFeatures

    alias: AliasedClass[DeclarativeT] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        """Initializes `self.alias` with an aliased version of the scoped model.

        This method creates an `AliasedClass` for the model specified in
        `self.scope.model`. The alias is named using `self.name` (typically the
        table name) and is created with `flat=True` to prevent nesting if the
        model is already an alias.
        """
        self.alias = aliased(class_mapper(self.scope.model), name=self.name, flat=True)

    @cached_property
    def _distinct_on_rank_column(self) -> str:
        """Provides a unique name for the rank column used in DISTINCT ON emulation.

        This name is generated using `self.scope.key("distinct_on_rank")` to ensure
        it doesn't clash with other column names within the current query scope.
        The result is cached for efficiency.

        Returns:
            A string representing the unique name for the rank column.
        """
        return self.scope.key("distinct_on_rank")

    def distinct_on_condition(self, aliased_subquery: AliasedClass[DeclarativeT]) -> ColumnElement[bool]:
        """Generates a SQLAlchemy filter condition to select rows with rank 1.

        This method is typically used after a window function (like `ROW_NUMBER()`)
        has assigned ranks to rows. It creates a condition to filter for rows
        where the column named by `self._distinct_on_rank_column` in the
        provided `aliased_subquery` is equal to 1.

        Args:
            aliased_subquery: The `AliasedClass` instance of the subquery
                that contains the rank column.

        Returns:
            A SQLAlchemy `ColumnElement[bool]` representing the filter condition
            (e.g., `rank_column == 1`).
        """
        return inspect(aliased_subquery).selectable.columns[self._distinct_on_rank_column] == 1

    @property
    def name(self) -> str:
        """The name for the subquery alias, typically the model's table name.

        Returns:
            The `__tablename__` attribute of the model in `self.scope`.
        """
        return self.scope.model.__tablename__

    def build(self, query_graph: QueryGraph[DeclarativeT], query: Query) -> AliasedClass[DeclarativeT]:
        """Builds a subquery (typically a CTE) for complex query scenarios.

        This method constructs a subquery based on the provided `query_graph`
        and `query` object. It's primarily used to handle situations like:
        - Emulating `DISTINCT ON` using a `ROW_NUMBER()` window function when
          `query.use_distinct_on` is True.
        - Ensuring correct pagination (limit/offset) when applied with complex
          joins or when `DISTINCT ON` is active.

        The process involves:
        1. Selecting an initial set of columns from `self.alias` based on `query_graph`.
        2. If `query.use_distinct_on`, adding a `ROW_NUMBER()` window function partitioned
           by distinct expressions and ordered by order_by expressions. The rank column
           is named using `self._distinct_on_rank_column`.
        3. Applying query hooks to the selected columns.
        4. Applying the main query components (joins, where, order by, limit, offset)
           from the `query` object to the subquery statement.
        5. Materializing the resulting statement as a Common Table Expression (CTE).

        Args:
            query_graph: The `QueryGraph` instance providing the overall query
                structure, including selection trees and distinct/order by nodes.
            query: The `Query` object containing specific components like filters,
                ordering, pagination settings, and the `use_distinct_on` flag.

        Returns:
            An `AliasedClass` representing the built subquery (CTE), ready to be
            used in further query construction (e.g., by joining it).
        """
        statement = select(inspect(self.alias)).options(raiseload("*"))
        only_columns: list[QueryableAttribute[Any] | NamedColumn[Any]] = [
            *self.scope.inspect(query_graph.root_join_tree).selection(self.alias),
            *[self.scope.aliased_attribute(node) for node in query_graph.order_by_nodes if not node.value.is_computed],
        ]
        # Add columns referenced in root aggregations
        if aggregation_tree := query_graph.root_aggregation_tree():
            only_columns.extend(
                self.scope.aliased_attribute(child)
                for child in aggregation_tree.leaves()
                if child.value.is_function_arg
            )
        for function_node in self.scope.referenced_function_nodes:
            only_columns.append(self.scope.columns[function_node])
            self.scope.columns[function_node] = self.scope.scoped_column(
                inspect(self.alias).selectable, self.scope.key(function_node)
            )

        if query.distinct_on and not query.use_distinct_on:
            order_by_expressions = query.order_by.expressions if query.order_by else []
            rank = (
                func.row_number()
                .over(partition_by=query.distinct_on.expressions, order_by=order_by_expressions or None)
                .label(self._distinct_on_rank_column)
            )
            only_columns.append(rank)

        statement = statement.with_only_columns(*only_columns)
        statement = dataclasses.replace(query, root_aggregation_functions=[]).statement(statement)
        statement, _ = self.hook_applier.apply(
            statement,
            node=query_graph.root_join_tree.root,
            alias=self.scope.root_alias,
            loading_mode="add",
            in_subquery=True,
        )

        return aliased(class_mapper(self.scope.model), statement.subquery(self.name), name=self.name)


@dataclass
class HookApplier:
    """Manages and applies query hooks to SQLAlchemy SELECT statements.

    This class is responsible for invoking registered `QueryHook` instances
    at appropriate points during the construction of a SQLAlchemy query.
    Hooks can modify the statement, for example, by adding columns, applying
    transformations, or changing loader options, based on the current
    `QueryNodeType` being processed.

    Attributes:
        scope: The `QueryScope` providing context (e.g., root model, database
            features) that might be relevant for hook execution.
        hooks: A `defaultdict` mapping `QueryNodeType` instances to a list of
            `QueryHook` objects. This allows multiple hooks to be registered
            and applied for the same node type.
    """

    scope: QueryScope[Any]
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
