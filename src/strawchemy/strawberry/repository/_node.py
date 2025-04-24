from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar, cast

from strawberry.types import get_object_definition
from strawberry.utils.typing import type_has_annotation
from strawchemy.dto.types import DTO_MISSING
from strawchemy.graphql.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.graphql.dto import (
    QueryNode,
)
from strawchemy.sqlalchemy import SQLAlchemyGraphQLRepository
from strawchemy.strawberry._instance import MapperModelInstance
from strawchemy.typing import DataclassProtocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from strawchemy.sqlalchemy._executor import NodeResult, QueryResult


__all__ = ("SQLAlchemyGraphQLRepository",)

T = TypeVar("T")


@dataclass(kw_only=True, eq=False, repr=False)
class _StrawberryQueryNode(QueryNode[Any, Any], Generic[T]):
    strawberry_type: type[T]
    children: list[Self] = dataclasses.field(default_factory=list)
    arguments: list[Self] = dataclasses.field(default_factory=list)

    def _model_instance_attribute(self) -> str | None:
        return next(
            (
                field.name
                for field in dataclasses.fields(cast(DataclassProtocol, self.strawberry_type))
                if type_has_annotation(field.type, MapperModelInstance)
            ),
            None,
        )

    @classmethod
    def _default_type_kwargs(cls, node: Self) -> dict[str, Any]:
        strawberry_definition = get_object_definition(node.strawberry_type, strict=True)
        return {field.name: DTO_MISSING for field in strawberry_definition.fields if field.init}

    def computed_value(self, node: _StrawberryQueryNode[T], result: NodeResult[Any] | QueryResult[Any]) -> T:
        strawberry_definition = get_object_definition(node.strawberry_type)
        if strawberry_definition is None:
            return result.value(node)
        kwargs: dict[str, Any] = {field.name: None for field in strawberry_definition.fields if field.init}
        for child in node.children:
            kwargs[child.value.name] = self.computed_value(child, result)
        return node.strawberry_type(**kwargs)

    def node_result_to_strawberry_type(self, node_result: NodeResult[Any]) -> T:
        kwargs = self._default_type_kwargs(self)
        for child in self.children:
            if child.value.is_computed:
                kwargs[child.value.name] = self.computed_value(child, node_result)
            elif child.value.is_relation:
                value = node_result.value(child)
                if isinstance(value, list | tuple):
                    kwargs[child.value.name] = [
                        child.node_result_to_strawberry_type(node_result.copy_with(element)) for element in value
                    ]
                elif value is not None:
                    kwargs[child.value.name] = child.node_result_to_strawberry_type(node_result.copy_with(value))
                else:
                    kwargs[child.value.name] = None
            else:
                kwargs[child.value.name] = node_result.value(child)
        if attribute := self._model_instance_attribute():
            kwargs[attribute] = node_result.model
        return self.strawberry_type(**kwargs)

    def query_result_to_strawberry_type(self, results: QueryResult[Any]) -> Sequence[T]:
        """Recursively constructs a sequence of Strawberry type instances from a query result.

        Args:
            results: The query result to convert.

        Returns:
            A sequence of Strawberry type instances.
        """
        return [self.node_result_to_strawberry_type(node_result) for node_result in results]

    def aggregation_query_result_to_strawberry_type(self, results: QueryResult[Any]) -> T:
        """Recursively constructs a Strawberry type instance from an aggregation query result.

        Args:
            results: The query result to convert.

        Returns:
            A Strawberry type instance.
        """
        kwargs: dict[str, Any] = {}
        nodes_child = self.find_child(lambda child: child.value.name == NODES_KEY)
        aggregations_child = self.find_child(lambda child: child.value.name == AGGREGATIONS_KEY)
        kwargs[NODES_KEY], kwargs[AGGREGATIONS_KEY] = [], None
        if nodes_child:
            kwargs[NODES_KEY] = [nodes_child.node_result_to_strawberry_type(node_results) for node_results in results]
        if aggregations_child:
            aggregations = self._default_type_kwargs(aggregations_child)
            aggregations.update(
                {child.value.name: child.computed_value(child, results) for child in aggregations_child.children}
            )
            kwargs[AGGREGATIONS_KEY] = aggregations_child.strawberry_type(**aggregations)
        return self.strawberry_type(**kwargs)
