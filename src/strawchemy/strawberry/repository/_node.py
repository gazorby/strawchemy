from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from strawberry.types import get_object_definition
from strawberry.utils.typing import type_has_annotation
from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY
from strawchemy.dto.types import DTO_MISSING
from strawchemy.graph import GraphError
from strawchemy.sqlalchemy import SQLAlchemyGraphQLRepository
from strawchemy.strawberry._instance import MapperModelInstance
from strawchemy.strawberry.dto import QueryNode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from strawchemy.sqlalchemy._executor import NodeResult, QueryResult
    from strawchemy.strawberry.typing import QueryNodeType
    from strawchemy.typing import DataclassProtocol


__all__ = ("SQLAlchemyGraphQLRepository", "StrawberryQueryNode")

T = TypeVar("T")


@dataclass(kw_only=True, eq=False, repr=False)
class StrawberryQueryNode(QueryNode, Generic[T]):
    @property
    def strawberry_type(self) -> type[T]:
        if self.metadata.data.strawberry_type is None:
            raise GraphError
        return self.metadata.data.strawberry_type

    def _model_instance_attribute(self) -> str | None:
        return next(
            (
                field.name
                for field in dataclasses.fields(cast("DataclassProtocol", self.strawberry_type))
                if type_has_annotation(field.type, MapperModelInstance)
            ),
            None,
        )

    @classmethod
    def _default_type_kwargs(cls, node: StrawberryQueryNode[Any]) -> dict[str, Any]:
        strawberry_definition = get_object_definition(node.strawberry_type, strict=True)
        return {field.name: DTO_MISSING for field in strawberry_definition.fields if field.init}

    def computed_value(self, node: QueryNodeType, result: NodeResult[Any] | QueryResult[Any]) -> T:
        strawberry_definition = get_object_definition(node.metadata.data.strawberry_type)
        if strawberry_definition is None or node.metadata.data.strawberry_type is None:
            return result.value(node)
        kwargs: dict[str, Any] = {field.name: None for field in strawberry_definition.fields if field.init}
        for child in node.children:
            kwargs[child.value.name] = self.computed_value(child, result)
        return node.metadata.data.strawberry_type(**kwargs)

    def node_result_to_strawberry_type(self, node_result: NodeResult[Any]) -> T:
        kwargs = self._default_type_kwargs(self)
        for child in self.children:
            if not isinstance(child, StrawberryQueryNode):
                continue
            if child.value.is_computed or child.metadata.data.is_transform:
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
        if isinstance(nodes_child, StrawberryQueryNode):
            kwargs[NODES_KEY] = [nodes_child.node_result_to_strawberry_type(node_results) for node_results in results]
        if isinstance(aggregations_child, StrawberryQueryNode):
            aggregations = self._default_type_kwargs(aggregations_child)
            aggregations.update(
                {
                    child.value.name: child.computed_value(child, results)
                    for child in aggregations_child.children
                    if isinstance(child, StrawberryQueryNode)
                }
            )
            kwargs[AGGREGATIONS_KEY] = aggregations_child.strawberry_type(**aggregations)
        return self.strawberry_type(**kwargs)
