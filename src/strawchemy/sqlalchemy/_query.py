from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, Self, cast

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
from sqlalchemy.orm import (
    QueryableAttribute,
    RelationshipDirection,
    RelationshipProperty,
    aliased,
    class_mapper,
    raiseload,
)
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql import ColumnElement, SQLColumnExpression
from sqlalchemy.sql.elements import NamedColumn
from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.graph import merge_trees
from strawchemy.strawberry.dto import (
    BooleanFilterDTO,
    EnumDTO,
    Filter,
    GraphQLFieldDefinition,
    OrderByDTO,
    OrderByEnum,
    QueryNode,
)

from .exceptions import TranspilingError
from .typing import DeclarativeT, OrderBySpec

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from sqlalchemy.sql._typing import _OnClauseArgument
    from sqlalchemy.sql.selectable import NamedFromClause
    from strawchemy.config.databases import DatabaseFeatures
    from strawchemy.strawberry.typing import QueryNodeType

    from ._scope import QueryScope
    from .hook import ColumnLoadingMode, QueryHook

__all__ = ("AggregationJoin", "Conjunction", "DistinctOn", "Join", "OrderBy", "QueryGraph", "Where")


@dataclass
class Join:
    target: QueryableAttribute[Any] | NamedFromClause | AliasedClass[Any]
    node: QueryNodeType
    onclause: _OnClauseArgument | None = None
    is_outer: bool = False
    order_nodes: list[QueryNodeType] = dataclasses.field(default_factory=list)

    @property
    def _selectable(self) -> NamedFromClause:
        if isinstance(self.target, AliasedClass):
            return cast("NamedFromClause", inspect(self.target).selectable)
        return self.target

    @property
    def _relationship(self) -> RelationshipProperty[Any]:
        return cast("RelationshipProperty[Any]", self.node.value.model_field.property)

    @property
    def order(self) -> int:
        return self.node.level

    @property
    def name(self) -> str:
        return self._selectable.name

    @property
    def to_many(self) -> bool:
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
    subquery_alias: AliasedClass[Any]

    _column_names: dict[str, int] = dataclasses.field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        for column in self._inner_select.selected_columns:
            if isinstance(column, NamedColumn):
                self._column_names[column.name] = 1

    @property
    def _inner_select(self) -> Select[Any]:
        if isinstance(self._selectable, CTE):
            return cast("Select[Any]", self._selectable.element)
        self_join = cast("AliasedReturnsRows", self._selectable)
        return cast("Select[Any]", cast("Subquery", self_join.element).element)

    def _existing_function_column(self, new_column: ColumnElement[Any]) -> ColumnElement[Any] | None:
        for column in self._inner_select.selected_columns:
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
        new_sub_select = self._inner_select.add_columns(self._ensure_unique_name(column))

        if isinstance(self._selectable, Lateral):
            new_sub_select = new_sub_select.lateral(self.name)
        else:
            new_sub_select = new_sub_select.cte(self.name)

        if isinstance(self.target, AliasedClass):
            inspect(self.target).selectable = new_sub_select
        else:
            self.target = new_sub_select

    def upsert_column_to_subquery(self, column: ColumnElement[Any]) -> tuple[ColumnElement[Any], bool]:
        if (existing := self._existing_function_column(column)) is not None:
            return existing, False
        self.add_column_to_subquery(column)
        return column, True


@dataclass
class QueryGraph(Generic[DeclarativeT]):
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
    expressions: list[ColumnElement[bool]] = dataclasses.field(default_factory=list)
    joins: list[Join] = dataclasses.field(default_factory=list)
    common_join_path: list[QueryNodeType] = dataclasses.field(default_factory=list)

    def has_many_predicates(self) -> bool:
        if not self.expressions:
            return False
        return len(self.expressions) > 1 or (
            isinstance(self.expressions[0], BooleanClauseList) and len(self.expressions[0]) > 1
        )


@dataclass
class Where:
    conjunction: Conjunction = dataclasses.field(default_factory=Conjunction)
    joins: list[Join] = dataclasses.field(default_factory=list)

    @property
    def expressions(self) -> list[ColumnElement[bool]]:
        return self.conjunction.expressions

    def clear_expressions(self) -> None:
        self.conjunction.expressions.clear()

    @classmethod
    def from_expressions(cls, *expressions: ColumnElement[bool]) -> Self:
        return cls(Conjunction(list(expressions)))


@dataclass
class OrderBy:
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
        expressions: list[UnaryExpression[Any]] = []
        for column, order_by in self.columns:
            expressions.extend(self._order_by(column, order_by))
        return expressions


@dataclass
class DistinctOn:
    query_graph: QueryGraph[Any]

    @property
    def _distinct_on_fields(self) -> list[GraphQLFieldDefinition]:
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

    def __bool__(self) -> bool:
        return bool(self.expressions)


@dataclass
class Query:
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
        distinct_expressions = self.distinct_on.expressions if self.distinct_on else []

        if self.use_distinct_on:
            # Add ORDER BY columns not present in the SELECT clause
            statement = statement.add_columns(
                *[
                    expression.element
                    for expression in order_by_expressions
                    if isinstance(expression.element, ColumnElement)
                    and not any(elem.compare(expression.element) for elem in statement.selected_columns)
                ]
            )
            statement = statement.distinct(*distinct_expressions)
        return statement

    @property
    def joins_have_many(self) -> bool:
        return next((True for join in self.joins if join.to_many), False)

    def statement(self, base_statement: Select[tuple[DeclarativeT]]) -> Select[tuple[DeclarativeT]]:
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
    scope: QueryScope[Any]
    hook_applier: HookApplier
    db_features: DatabaseFeatures

    alias: AliasedClass[DeclarativeT] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.alias = aliased(class_mapper(self.scope.model), name=self.name, flat=True)

    @cached_property
    def _distinct_on_rank_column(self) -> str:
        return self.scope.key("distinct_on_rank")

    def distinct_on_condition(self) -> ColumnElement[bool]:
        return self.scope.literal_column(self.name, self._distinct_on_rank_column) == 1

    @property
    def name(self) -> str:
        return self.scope.model.__tablename__

    def build(self, query_graph: QueryGraph[DeclarativeT], query: Query) -> AliasedClass[DeclarativeT]:
        """Creates a subquery from the root alias for pagination.

        This method is used when pagination (limit or offset) is applied at the root level.
        It constructs a subquery using the root alias and applies necessary selections,
        column transformations, before returning an aliased class
        representing the subquery. This allows for correct pagination when dealing
        with complex queries involving joins and aggregations.

        Args:
            query_graph: The query graph representing the entire query structure.
            query: The `Query` object containing query components like joins,
                where clauses, and order by clauses.

        Returns:
            An aliased class representing the subquery, which can be used in further
            query construction.
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
            self.scope.columns[function_node] = self.scope.literal_column(self.name, self.scope.key(function_node))

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
        options: list[_AbstractLoad] = []
        for hook in self.hooks[node]:
            statement = hook.apply_hook(statement, alias)
            statement, column_options = hook.load_columns(statement, alias, loading_mode)
            options.extend(column_options)
            if not in_subquery:
                options.extend(hook.load_relationships(self.scope.alias_from_relation_node(node, "target")))
        return statement, options
