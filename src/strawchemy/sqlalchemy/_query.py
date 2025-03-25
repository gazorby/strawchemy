from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, Self, cast

from sqlalchemy import AliasedReturnsRows, BooleanClauseList, Label, Select, Subquery, UnaryExpression, inspect
from sqlalchemy.orm import DeclarativeBase, QueryableAttribute, RelationshipDirection, RelationshipProperty
from sqlalchemy.sql import ColumnElement, SQLColumnExpression
from sqlalchemy.sql.elements import NamedColumn
from sqlalchemy.sql.visitors import replacement_traverse
from strawchemy.graph import merge_trees
from strawchemy.graphql.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.graphql.dto import (
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)
from strawchemy.sqlalchemy.exceptions import TranspilingError

from .typing import DeclarativeT

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass
    from sqlalchemy.sql._typing import _OnClauseArgument
    from sqlalchemy.sql.selectable import NamedFromClause
    from strawchemy.sqlalchemy._scope import QueryScope
    from strawchemy.sqlalchemy.typing import SQLAlchemyOrderByNode, SQLAlchemyQueryNode

__all__ = ("AggregationJoin", "Conjunction", "DistinctOn", "Join", "OrderBy", "QueryGraph", "Where")


@dataclass
class Join:
    join: QueryableAttribute[Any] | NamedFromClause
    node: SQLAlchemyQueryNode
    onclause: _OnClauseArgument | None = None
    is_outer: bool = False

    @property
    def order(self) -> int:
        return self.node.level

    @property
    def name(self) -> str:
        return self.join.name

    @property
    def relationship(self) -> RelationshipProperty[Any]:
        return cast(RelationshipProperty[Any], self.node.value.model_field.property)

    @property
    def to_many(self) -> bool:
        return self.relationship.direction in {
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
    subquery_alias: AliasedClass[Any]

    _column_names: dict[str, int] = dataclasses.field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        for column in self._lateral_select.selected_columns:
            if isinstance(column, NamedColumn):
                self._column_names[column.name] = 1

    @property
    def _lateral_select(self) -> Select[Any]:
        self_join = cast(AliasedReturnsRows, self.join)
        return cast(Select[Any], cast(Subquery, self_join.element).element)

    def _existing_function_column(self, new_column: ColumnElement[Any]) -> ColumnElement[Any] | None:
        for column in self._lateral_select.selected_columns:
            base_columns = column.base_columns
            new_base_columns = new_column.base_columns
            if len(base_columns) != len(new_base_columns):
                continue
            for first, other in zip(base_columns, new_base_columns, strict=True):
                if not first.compare(other):
                    break
            else:
                return column
        return None

    def _ensure_unique_name(self, column: ColumnElement[Any]) -> ColumnElement[Any]:
        if not isinstance(column, NamedColumn):
            return column
        if count := self._column_names.get(column.name):
            name = f"{column.name}_{count}"
            self._column_names[column.name] += 1
        else:
            name = column.name
        return column.label(name)

    def add_column_to_subquery(self, column: ColumnElement[Any]) -> None:
        self_join = cast(AliasedReturnsRows, self.join)
        new_sub_select = self._lateral_select.add_columns(self._ensure_unique_name(column))

        def _replace(
            element: Subquery[Any],
            _join: AliasedReturnsRows = self_join,
            new: Select[Any] = new_sub_select,
            **_: Any,
        ) -> Subquery[Any] | None:
            if element is _join.element:
                element.element = new
                return element
            return None

        replacement_traverse(self.join, {}, _replace)

    def upsert_column_to_subquery(self, column: ColumnElement[Any]) -> tuple[ColumnElement[Any], bool]:
        if (existing := self._existing_function_column(column)) is not None:
            return existing, False
        self.add_column_to_subquery(column)
        return column, True


@dataclass
class QueryGraph(Generic[DeclarativeT]):
    scope: QueryScope[DeclarativeT]
    selection_tree: SQLAlchemyQueryNode | None = None
    order_by: list[OrderByDTO[DeclarativeBase, QueryableAttribute[Any]]] = dataclasses.field(default_factory=list)
    distinct_on: list[EnumDTO] = dataclasses.field(default_factory=list)
    dto_filter: BooleanFilterDTO[DeclarativeBase, QueryableAttribute[Any]] | None = None

    query_filter: Filter[DeclarativeBase, QueryableAttribute[Any]] | None = dataclasses.field(init=False, default=None)
    where_join_tree: SQLAlchemyQueryNode | None = dataclasses.field(init=False, default=None)
    subquery_join_tree: SQLAlchemyQueryNode | None = dataclasses.field(init=False, default=None)
    root_join_tree: SQLAlchemyQueryNode = dataclasses.field(init=False)
    order_by_nodes: list[SQLAlchemyOrderByNode] = dataclasses.field(init=False, default_factory=list)

    def __post_init__(self) -> None:
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

    def resolved_selection_tree(self) -> SQLAlchemyQueryNode:
        tree = self.selection_tree
        if tree and tree.query_metadata.root_aggregations:
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
    def order_by_tree(self) -> SQLAlchemyOrderByNode | None:
        """Creates a query node tree from a list of order by DTOs.

        Args:
            dtos: List of order by DTOs to create the tree from.

        Returns:
            A query node tree representing the order by clauses, or None if no DTOs provided.
        """
        merged_tree: SQLAlchemyOrderByNode | None = None
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

    def root_aggregation_tree(self) -> SQLAlchemyQueryNode | None:
        if self.selection_tree:
            return self.selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        return None


@dataclass
class Where:
    conjunction: Conjunction
    joins: list[Join] = dataclasses.field(default_factory=list)

    @property
    def expressions(self) -> list[ColumnElement[bool]]:
        return self.conjunction.expressions

    def clear_expressions(self) -> None:
        self.conjunction.expressions.clear()


@dataclass
class OrderBy:
    columns: list[tuple[SQLColumnExpression[Any], OrderByEnum]] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)

    @classmethod
    def _order_by(cls, column: SQLColumnExpression[Any], order_by: OrderByEnum) -> UnaryExpression[Any]:
        """Creates an order by expression for a given node and attribute.

        Args:
            column: The order by enum value (ASC, DESC, etc.).
            order_by: The column or attribute to order by.

        Returns:
            A unary expression representing the order by clause.
        """
        if order_by is OrderByEnum.ASC:
            return column.asc()
        if order_by is OrderByEnum.ASC_NULLS_FIRST:
            return column.asc().nulls_first()
        if order_by is OrderByEnum.ASC_NULLS_LAST:
            return column.asc().nulls_last()
        if order_by is OrderByEnum.DESC:
            return column.desc()
        if order_by is OrderByEnum.DESC_NULLS_FIRST:
            return column.desc().nulls_first()
        return column.desc().nulls_last()

    @cached_property
    def expressions(self) -> list[UnaryExpression[Any]]:
        return [self._order_by(column, order_by) for column, order_by in self.columns]


@dataclass
class DistinctOn:
    query_graph: QueryGraph[Any]

    @property
    def _distinct_on_fields(self) -> list[GraphQLFieldDefinition[Any, Any]]:
        return [enum.field_definition for enum in self.query_graph.distinct_on]

    @property
    def expressions(self) -> list[QueryableAttribute[Any]]:
        """Creates DISTINCT ON expressions from a list of fields.

        Args:
            distinct_on_fields: The fields to create distinct expressions from.
            order_by_nodes: The order by nodes to validate against.

        Returns:
            A list of attributes for the DISTINCT ON clause.

        Raises:
            TranspilingError: If distinct fields don't match leftmost order by fields.
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


@dataclass
class Conjunction:
    expressions: list[ColumnElement[bool]]
    joins: list[Join] = dataclasses.field(default_factory=list)
    common_join_path: list[SQLAlchemyQueryNode] = dataclasses.field(default_factory=list)

    def has_many_predicates(self) -> bool:
        if not self.expressions:
            return False
        return len(self.expressions) > 1 or (
            isinstance(self.expressions[0], BooleanClauseList) and len(self.expressions[0]) > 1
        )


@dataclass
class Query:
    joins: list[Join] = dataclasses.field(default_factory=list)
    where: Where | None = None
    order_by: OrderBy | None = None
    distinct_on: DistinctOn | None = None
    root_aggregation_functions: list[Label[Any]] = dataclasses.field(default_factory=list)
    limit: int | None = None
    offset: int | None = None

    @property
    def joins_have_many(self) -> bool:
        return next((True for join in self.joins if join.to_many), False)

    def statement(self, base_statement: Select[tuple[DeclarativeT]]) -> Select[tuple[DeclarativeT]]:
        sorted_joins = sorted(self.joins or [])
        distinct_expressions = self.distinct_on.expressions if self.distinct_on else []
        order_by_expressions = self.order_by.expressions if self.order_by else []

        for element in sorted_joins:
            base_statement = base_statement.join(element.join, onclause=element.onclause, isouter=element.is_outer)
        if self.where and self.where.expressions:
            base_statement = base_statement.where(*self.where.expressions)
        if order_by_expressions:
            base_statement = base_statement.order_by(*order_by_expressions)
        if distinct_expressions:
            # Add ORDER BY columns not present in the SELECT clause
            base_statement = base_statement.add_columns(
                *[
                    expression.element
                    for expression in order_by_expressions
                    if isinstance(expression.element, ColumnElement)
                    and not any(elem.compare(expression.element) for elem in base_statement.selected_columns)
                ]
            )
            base_statement = base_statement.distinct(*distinct_expressions)
        if self.limit is not None:
            base_statement = base_statement.limit(self.limit)
        if self.offset is not None:
            base_statement = base_statement.offset(self.offset)

        return base_statement.add_columns(*self.root_aggregation_functions)
