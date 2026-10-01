"""The client input of one query level, frozen, which every pass reads."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.dto.inspectors import SQLAlchemyInspector
from strawchemy.dto.strawberry import GraphQLFieldDefinition, QueryNode
from strawchemy.dto.types import DTOConfig, Purpose
from strawchemy.transpiler._core.functions import AggregateFunction
from strawchemy.transpiler._core.split import FilterScope, FilterSplit, split_filter
from strawchemy.utils.graph import merge_trees

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.orm import DeclarativeBase, RelationshipProperty

    from strawchemy.dto.strawberry import BooleanFilterDTO, EnumDTO, OrderByDTO
    from strawchemy.typing import QueryNodeType

__all__ = ("QueryRequest",)


@dataclass(frozen=True)
class QueryRequest:
    """What a GraphQL query selects, filters and orders by at one level; it holds no join."""

    model: type[DeclarativeBase]
    selection_tree: QueryNodeType | None
    dto_filter: BooleanFilterDTO | None
    order_by: tuple[OrderByDTO, ...]
    distinct_on: tuple[EnumDTO, ...]
    limit: int | None
    offset: int | None
    allow_null: bool
    filter_scope: FilterScope = "query"
    """Statement the filter restricts; ``exists`` is the body of an EXISTS, which keeps every branch it can test."""

    @cached_property
    def _aggregations(
        self,
    ) -> tuple[dict[QueryNodeType, dict[QueryNodeType, AggregateFunction]], dict[QueryNodeType, set[QueryNodeType]]]:
        """Functions and selected function nodes of every aggregation node, gathered once."""
        functions: dict[QueryNodeType, dict[QueryNodeType, AggregateFunction]] = {}
        selected: dict[QueryNodeType, set[QueryNodeType]] = {}

        for query_filter in self.filter_split.filters():
            for aggregation in query_filter.iter_aggregation_filters():
                aggregation_node = aggregation.field_node.find_parent(lambda node: node.value.is_aggregate, strict=True)
                function = AggregateFunction.for_filter(aggregation.field_node, distinct=aggregation.distinct)
                functions.setdefault(aggregation_node, {}).setdefault(function.node, function)

        order_by_aggregations = (
            node.find_parent(lambda node: node.value.is_aggregate, strict=True)
            for node in self.order_by_nodes
            if node.value.is_function or node.value.is_function_arg
        )
        selection_aggregations = (node for node in self.selection.iter_depth_first() if node.value.is_aggregate)
        sources = (
            *((node, False) for node in order_by_aggregations),
            *((node, True) for node in selection_aggregations),
        )
        for aggregation_node, is_selection in sources:
            node_functions = functions.setdefault(aggregation_node, {})
            for function_node in aggregation_node.children:
                for function in AggregateFunction.for_selection(function_node):
                    node_functions.setdefault(function.node, function)
                    if is_selection:
                        selected.setdefault(aggregation_node, set()).add(function.node)

        return functions, selected

    @cached_property
    def filter_split(self) -> FilterSplit:
        """The filter divided for the scope by ``split_filter``."""
        return split_filter(self.dto_filter, self.filter_scope)

    @classmethod
    def for_relation(cls, node: QueryNodeType) -> QueryRequest:
        """Creates the request of the level behind a relation node, from the arguments of its field."""
        relation_filter = node.metadata.data.relation_filter
        relationship = cast("RelationshipProperty[Any]", node.value.model_field.property)
        return cls(
            model=relationship.mapper.class_,
            selection_tree=node,
            dto_filter=None,
            order_by=tuple(relation_filter.order_by),
            distinct_on=tuple(relation_filter.distinct_on),
            limit=relation_filter.limit,
            offset=relation_filter.offset,
            allow_null=False,
        )

    @cached_property
    def selection(self) -> QueryNodeType:
        """The selection tree of the listed rows, or a tree of the primary keys when nothing is selected."""
        tree = self.selection_tree
        if tree and tree.is_root and tree.graph_metadata.metadata.root_aggregations:
            tree = tree.find_child(lambda child: child.value.name == NODES_KEY)
        if tree is None:
            tree = QueryNode.root_node(self.model)
            inspector = SQLAlchemyInspector([self.model.registry])
            for pk in SQLAlchemyInspector.pk_attributes(self.model.__mapper__):
                tree.insert_child(
                    GraphQLFieldDefinition.from_field(inspector.field_definition(pk, DTOConfig(Purpose.READ)))
                )
        return tree

    @property
    def orders_rows(self) -> bool:
        """Tells whether the request orders, paginates or deduplicates its rows."""
        return bool(self.order_by_nodes or self.distinct_on) or self.limit is not None or self.offset is not None

    @cached_property
    def order_by_nodes(self) -> tuple[QueryNodeType, ...]:
        """The order-by leaves, in the order the client gave them."""
        merged_tree: QueryNodeType | None = None
        max_order = 0
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
        return tuple(sorted(merged_tree.leaves())) if merged_tree is not None else ()

    @cached_property
    def root_aggregation_tree(self) -> QueryNodeType | None:
        """The ``aggregations`` subtree of the selection, if the client asked for root aggregations."""
        if self.selection_tree:
            return self.selection_tree.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        return None

    def aggregate_functions(self, aggregation_node: QueryNodeType) -> Mapping[QueryNodeType, AggregateFunction]:
        """Returns every function the filter, the ordering and the selection use on ``aggregation_node``.

        A function used by several of them is kept once, under its function node.
        """
        return self._aggregations[0].get(aggregation_node, {})

    def selected_functions(self, aggregation_node: QueryNodeType) -> frozenset[QueryNodeType]:
        """Returns the function nodes of ``aggregation_node`` that the client selected."""
        return frozenset(self._aggregations[1].get(aggregation_node, ()))
