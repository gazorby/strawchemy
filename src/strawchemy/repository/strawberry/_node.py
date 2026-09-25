from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from strawberry.types import get_object_definition
from strawberry.utils.typing import type_has_annotation

from strawchemy.constants import AGGREGATIONS_KEY, NODES_KEY, RESPONSE_VALUES_ATTRIBUTE
from strawchemy.dto.strawberry import QueryNode
from strawchemy.dto.types import DTOMissing
from strawchemy.exceptions import GraphError
from strawchemy.instance import MapperModelInstance
from strawchemy.repository.sqlalchemy import SQLAlchemyGraphQLRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from strawchemy.transpiler import NodeResult, QueryResult
    from strawchemy.typing import DataclassProtocol, QueryNodeType

__all__ = ("SQLAlchemyGraphQLRepository", "StrawberryQueryNode")

T = TypeVar("T")


@dataclass(eq=False, repr=False)
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
        return {field.name: DTOMissing for field in strawberry_definition.fields if field.init}

    def computed_value(self, node: QueryNodeType, result: NodeResult[Any] | QueryResult[Any]) -> T:
        strawberry_definition = get_object_definition(node.metadata.data.strawberry_type)
        if strawberry_definition is None or node.metadata.data.strawberry_type is None:
            return result.value(node)
        kwargs: dict[str, Any] = {field.name: None for field in strawberry_definition.fields if field.init}
        for child in node.children:
            kwargs[child.value.name] = self.computed_value(child, result)
        return node.metadata.data.strawberry_type(**kwargs)

    def _child_value(self, child: StrawberryQueryNode[Any], node_result: NodeResult[Any]) -> object:
        if child.value.is_computed or child.metadata.data.is_transform:
            return self.computed_value(child, node_result)
        if not child.value.is_relation:
            return node_result.value(child)
        value = node_result.value(child)
        if isinstance(value, (list, tuple)):
            return [child.node_result_to_strawberry_type(node_result.copy_with(child, element)) for element in value]
        if value is not None:
            return child.node_result_to_strawberry_type(node_result.copy_with(child, value))
        return None

    @cached_property
    def _shared_field_names(self) -> frozenset[str]:
        names = Counter(child.value.name for child in self.children if isinstance(child, StrawberryQueryNode))
        return frozenset(name for name, count in names.items() if count > 1)

    def node_result_to_strawberry_type(self, node_result: NodeResult[Any]) -> T:
        kwargs = self._default_type_kwargs(self)
        shared_field_names = self._shared_field_names
        response_values: dict[str, Any] = {}
        for child in [child for child in self.children if isinstance(child, StrawberryQueryNode)]:
            kwargs[child.value.name] = value = self._child_value(child, node_result)
            if child.value.name in shared_field_names:
                response_values.update(dict.fromkeys(child.metadata.data.response_keys, value))
        if attribute := self._model_instance_attribute():
            kwargs[attribute] = node_result.model
        instance = self.strawberry_type(**kwargs)
        # Children sharing a field name differ by arguments; the field resolver picks the value by response key.
        if response_values:
            setattr(instance, RESPONSE_VALUES_ATTRIBUTE, response_values)
        return instance

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
