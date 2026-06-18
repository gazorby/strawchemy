"""Data transfer objects (DTOs) for GraphQL operations.

This module defines a set of data transfer objects (DTOs) and related
utilities specifically designed for use with GraphQL APIs. These DTOs
provide a structured way to represent data when constructing GraphQL
queries and mutations, as well as when processing responses from a
GraphQL server.

Key components of this module include:

- GraphQLField: A class that extends the base DTOField to provide
  GraphQL-specific metadata and functionality.
- QueryNode: A class that represents a node in a GraphQL query tree,
  allowing for the construction of complex queries with nested
  relationships and filters.
- Filter, OrderBy, and Aggregate DTOs: Classes that define the
  structure of GraphQL filters, orderings, and aggregations,
  respectively.
- Utility functions: Functions for manipulating DTOs and query trees,
  such as _ensure_list and DTOKey.

This module aims to simplify the process of working with GraphQL APIs
by providing a set of reusable DTOs and tools that can be easily
adapted to different GraphQL schemas.
"""

from __future__ import annotations

import dataclasses
from copy import copy
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar, cast, overload

import strawberry
from msgspec import Struct, field, json
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, QueryableAttribute
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import UnaryExpression
from typing_extensions import Self, override

from strawchemy.dto.backend.strawberry import MappedStrawberryDTO, StrawberryDTO
from strawchemy.dto.base import DTOBase, DTOFieldDefinition, ModelFieldT, ModelT
from strawchemy.dto.types import DTOConfig, DTOFieldConfig, DTOMissing, Purpose
from strawchemy.exceptions import StrawchemyFieldError
from strawchemy.transpiler.hook import (
    QueryHook,  # noqa: TC001 msgspec does not support resolving references dynamically
)
from strawchemy.typing import (
    AggregationFunction,
    AggregationType,
    FunctionInfo,
    GraphQLPurpose,
    OrderByDTOT,
    OrderByExpr,
    QueryNodeType,
)
from strawchemy.utils.graph import AnyNode, GraphMetadata, MatchOn, Node, NodeMetadata, NodeT
from strawchemy.utils.text import camel_to_snake

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence

    from sqlalchemy import ColumnElement

    from strawchemy.schema.filters import EqualityComparison, GraphQLComparison

T = TypeVar("T")


class _ArgumentValue:
    __field_definitions__: ClassVar[dict[str, DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]]

    value: str


class RelationFilterDTO(Struct, frozen=True, dict=True):
    limit: int | None = None
    offset: int | None = None

    @cached_property
    def _json(self) -> bytes:
        return json.encode(self)

    def __bool__(self) -> bool:
        return bool(self.limit or self.offset)

    @override
    def __hash__(self) -> int:
        return hash(self._json)


@dataclass
class QueryGraphMetadata:
    root_aggregations: bool = False


@dataclass
class QueryNodeMetadata:
    relation_filter: RelationFilterDTO = dataclasses.field(default_factory=RelationFilterDTO)
    order_by: OrderByEnum | None = None
    strawberry_type: type[Any] | None = None
    json_path: str | None = None

    @property
    def is_transform(self) -> bool:
        return bool(self.json_path)


@dataclass(slots=True)
class StrawchemyDefinition:
    description: str = "GraphQL type"
    is_root_aggregation_type: bool = False
    field_map: dict[DTOKey, GraphQLFieldDefinition] = dataclasses.field(default_factory=dict)
    query_hook: QueryHook[Any] | list[QueryHook[Any]] | None = None
    filter: type[Any] | None = None
    order_by: type[Any] | None = None
    distinct_on: type[Any] | None = None
    purpose: GraphQLPurpose | None = None

    def __copy__(self) -> StrawchemyDefinition:
        return dataclasses.replace(self, field_map=dict(self.field_map))

    def populate_fields(
        self,
        key_source: type[Any] | DTOKey,
        fields: Iterable[GraphQLFieldDefinition],
    ) -> Self:
        key = key_source if isinstance(key_source, DTOKey) else DTOKey([key_source])
        self.field_map = {key + f.name: f for f in fields}
        return self

    def get_field(self, key: DTOKey, name: str | None = None) -> GraphQLFieldDefinition:
        full_key = key + name if name else key
        return self.field_map[full_key]

    def get_field_or_none(self, key: DTOKey, name: str | None = None) -> GraphQLFieldDefinition | None:
        full_key = key + name if name else key
        return self.field_map.get(full_key)

    @property
    def query_hooks(self) -> list[QueryHook[Any]]:
        if self.query_hook is None:
            return []
        if isinstance(self.query_hook, list):
            return cast("list[QueryHook[Any]]", list(self.query_hook))
        return [self.query_hook]

    @property
    def is_update_purpose(self) -> bool:
        return self.purpose in ("update_by_pk_input", "update_by_filter_input")


class StrawchemyObject:
    __strawchemy_definition__: ClassVar[StrawchemyDefinition]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        existing = cls.__dict__.get("__strawchemy_definition__")
        if existing is None:
            cls.__strawchemy_definition__ = StrawchemyDefinition()
        else:
            cls.__strawchemy_definition__ = copy(existing)


class _Key(Generic[T]):
    """A class to represent a key with multiple components.

    The key is a sequence of components joined by a separator (default: ":").
    It can be constructed from a sequence of components or a single string.
    Components can be of any type, but must be convertible to a string.

    The key can be extended with additional components using the `extend` or
    `append` methods. The key can also be concatenated with another key or a
    string using the `+` operator.

    The key can be converted to a string using the `str` function or the
    `to_str` method.

    Subclasses should implement the `to_str` method to convert a component to a
    string.
    """

    __slots__ = ("_key",)

    separator: ClassVar[str] = ":"

    def __init__(self, components: Sequence[T | str] | str | None = None) -> None:
        self._key: str = ""
        if isinstance(components, str):
            self._key = components
        elif components:
            self._key = str(self.extend(components))

    def _components_to_str(self, objects: Sequence[T | str]) -> Sequence[str]:
        return [obj if isinstance(obj, str) else self.to_str(obj) for obj in objects]

    def to_str(self, obj: T) -> str:
        raise NotImplementedError

    def append(self, component: T | str) -> Self:
        return self.extend([component])

    def extend(self, components: Sequence[T | str]) -> Self:
        str_components = self._components_to_str(components)
        self._key = self.separator.join([self._key, *str_components] if self._key else str_components)
        return self

    def __add__(self, other: Self | str) -> Self:
        if isinstance(other, str):
            return self.__class__((self._key, other))
        return self.__class__((self._key, other._key))

    @override
    def __str__(self) -> str:
        return self._key

    @override
    def __hash__(self) -> int:
        return hash(str(self))

    @override
    def __eq__(self, other: object) -> bool:
        return hash(self) == hash(other)

    @override
    def __ne__(self, other: object) -> bool:
        return hash(self) != hash(other)


class DTOKey(_Key[type[Any]]):
    @override
    def to_str(self, obj: type[Any]) -> str:
        return obj.__name__

    @classmethod
    def from_dto_node(cls, node: Node[Any, Any]) -> Self:
        return cls([node.value.model])

    @classmethod
    def from_query_node(cls, node: QueryNodeType) -> Self:
        if node.is_root:
            return cls([node.value.model])
        if node.value.related_model:
            return cls([node.value.related_model])
        return cls([node.value.model])


class OrderByRelationFilterDTO(RelationFilterDTO, Generic[OrderByDTOT], frozen=True):
    order_by: tuple[OrderByDTOT, ...] = field(default_factory=tuple)

    @override
    def __bool__(self) -> bool:
        return bool(self.limit or self.offset or self.order_by)


@dataclass
class OutputFunctionInfo:
    function: AggregationFunction
    output_type: Any
    require_arguments: bool = True
    default: Any = DTOMissing


@dataclass
class FilterFunctionInfo:
    function: AggregationFunction
    enum_fields: type[EnumDTO]
    aggregation_type: AggregationType
    comparison_type: type[GraphQLComparison]
    require_arguments: bool = True

    field_name_: str | None = None

    @property
    def field_name(self) -> str:
        if self.field_name_ is None:
            return self.function
        return self.field_name_


@dataclass(eq=False, repr=False)
class GraphQLFieldDefinition(DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]):
    is_aggregate: bool = False
    is_function: bool = False
    is_function_arg: bool = False

    _function: FunctionInfo | None = None

    def _hash_identity(self) -> Hashable:
        return (
            self.model_identity,
            self.is_relation,
            self.init,
            self.uselist,
            self.model_field_name,
            self.is_aggregate,
            self.is_function,
            self.is_function_arg,
        )

    @classmethod
    def from_field(cls, field_def: DTOFieldDefinition[ModelT, ModelFieldT], **kwargs: Any) -> Self:
        return cls(
            **{
                dc_field.name: getattr(field_def, dc_field.name)
                for dc_field in dataclasses.fields(field_def)
                if dc_field.init
            }
            | kwargs,
        )

    @property
    def is_computed(self) -> bool:
        return self.is_function or self.is_function_arg or self.is_aggregate

    @overload
    def function(self, strict: Literal[False]) -> FunctionInfo | None: ...

    @overload
    def function(self, strict: Literal[True]) -> FunctionInfo: ...

    @overload
    def function(self, strict: bool = False) -> FunctionInfo | None: ...

    def function(self, strict: bool = False) -> FunctionInfo | None:
        if not strict:
            return self._function
        if self._function is None:
            msg = "This node is not a function"
            raise ValueError(msg)
        return self._function

    @override
    def __hash__(self) -> int:
        return hash(self._hash_identity())

    @override
    def __eq__(self, other: object) -> bool:
        return hash(self) == hash(other)

    @override
    def __ne__(self, other: object) -> bool:
        return hash(self) != hash(other)


@dataclass(eq=False, repr=False)
class AggregateFieldDefinition(GraphQLFieldDefinition):
    is_relation: bool = True
    is_aggregate: bool = True


@dataclass(eq=False, repr=False)
class FunctionFieldDefinition(GraphQLFieldDefinition):
    is_relation: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        self.is_function = True

    @override
    @classmethod
    def from_field(
        cls,
        field_def: DTOFieldDefinition[ModelT, ModelFieldT],
        *,
        function: FilterFunctionInfo | OutputFunctionInfo | None = None,
        **kwargs: Any,
    ) -> Self:
        if function is None:
            msg = "FunctionFieldDefinition.from_field requires `function`"
            raise ValueError(msg)
        return super().from_field(field_def, _function=function, **kwargs)

    @override
    def _hash_identity(self) -> Hashable:
        return (
            super()._hash_identity(),
            self.function(strict=True).function,
            self.function(strict=True).require_arguments,
        )


@dataclass(eq=False, repr=False)
class FunctionArgFieldDefinition(FunctionFieldDefinition):
    def __post_init__(self) -> None:
        super().__post_init__()
        self.is_function_arg = True


@dataclass(eq=False)
class QueryNode(Node[GraphQLFieldDefinition, QueryNodeMetadata]):
    node_metadata: NodeMetadata[QueryNodeMetadata] | None = dataclasses.field(
        default_factory=lambda: NodeMetadata(QueryNodeMetadata())
    )
    graph_metadata: GraphMetadata[QueryGraphMetadata] = dataclasses.field(
        default_factory=lambda: GraphMetadata(QueryGraphMetadata())
    )

    @classmethod
    @override
    def _node_hash_identity(cls, node: Node[GraphQLFieldDefinition, QueryNodeMetadata]) -> Hashable:
        return super()._node_hash_identity(node), node.metadata.data.relation_filter

    @override
    def _update_new_child(self, child: NodeT) -> NodeT:
        super()._update_new_child(child)
        if self.value.is_function:
            child.value = FunctionArgFieldDefinition.from_field(child.value, function=self.value.function(strict=True))
        return child

    @override
    @classmethod
    def match_nodes(
        cls,
        left: AnyNode,
        right: AnyNode,
        match_on: Callable[[AnyNode, AnyNode], bool] | MatchOn,
    ) -> bool:
        if match_on == "value_equality":
            return left.value.model is right.value.model and left.value.model_field_name == right.value.model_field_name
        return super(cls, cls).match_nodes(left, right, match_on)

    @classmethod
    def root_node(
        cls,
        model: type[DeclarativeBase],
        root_aggregations: bool = False,
        strawberry_type: type[Any] | None = None,
    ) -> Self:
        root_name = camel_to_snake(model.__name__)
        field_def = GraphQLFieldDefinition(
            config=DTOFieldConfig(),
            dto_config=DTOConfig(Purpose.READ),
            model=model,
            model_field_name=root_name,
            is_relation=False,
            type_hint=model,
        )
        return cls(
            value=field_def,
            graph_metadata=GraphMetadata(QueryGraphMetadata(root_aggregations=root_aggregations)),
            node_metadata=NodeMetadata(QueryNodeMetadata(strawberry_type=strawberry_type)),
        )

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.value.model_field_name}>"


@dataclass
class AggregationFilter:
    function_info: FilterFunctionInfo
    predicate: EqualityComparison[Any]
    field_node: QueryNodeType
    distinct: bool | None = None


@dataclass
class Filter:
    and_: list[Self | GraphQLComparison | AggregationFilter] = dataclasses.field(default_factory=list)
    or_: list[Self] = dataclasses.field(default_factory=list)
    not_: Self | None = None

    def __bool__(self) -> bool:
        return bool(self.and_ or self.or_ or self.not_)

    def iter_aggregation_filters(self) -> Iterator[AggregationFilter]:
        """Yields every ``AggregationFilter`` in this filter tree in traversal order.

        Walks the ``and_``, ``or_`` and ``not_`` branches depth-first.

        Yields:
            Each aggregation filter found under the AND, OR and NOT branches.
        """
        for value in self.and_:
            if isinstance(value, AggregationFilter):
                yield value
            elif isinstance(value, Filter):
                yield from value.iter_aggregation_filters()
        for value in self.or_:
            yield from value.iter_aggregation_filters()
        if self.not_ is not None:
            yield from self.not_.iter_aggregation_filters()


class OrderByEnum(Enum):
    ASC = "ASC"
    ASC_NULLS_FIRST = "ASC_NULLS_FIRST"
    ASC_NULLS_LAST = "ASC_NULLS_LAST"
    DESC = "DESC"
    DESC_NULLS_FIRST = "DESC_NULLS_FIRST"
    DESC_NULLS_LAST = "DESC_NULLS_LAST"


@dataclass(frozen=True, slots=True)
class _DecomposedOrderBy:
    """A ``default_order_by`` expression broken into its column, direction and source element."""

    key: str
    """Attribute key of the ordered column."""
    order: OrderByEnum
    """Ordering direction, including nulls placement."""
    element: InstrumentedAttribute[Any] | ColumnElement[Any]
    """Underlying SQLAlchemy column element, with asc/desc/nulls modifiers stripped."""

    @classmethod
    def from_parts(
        cls,
        key: str,
        descending: bool,
        nulls: Literal["first", "last"] | None,
        element: InstrumentedAttribute[Any] | ColumnElement[Any],
    ) -> Self:
        """Builds an instance, resolving the ``OrderByEnum`` from direction and nulls placement."""
        match (descending, nulls):
            case (False, None):
                order = OrderByEnum.ASC
            case (False, "first"):
                order = OrderByEnum.ASC_NULLS_FIRST
            case (False, "last"):
                order = OrderByEnum.ASC_NULLS_LAST
            case (True, None):
                order = OrderByEnum.DESC
            case (True, "first"):
                order = OrderByEnum.DESC_NULLS_FIRST
            case _:  # (True, "last")
                order = OrderByEnum.DESC_NULLS_LAST
        return cls(key=key, order=order, element=element)


def decompose_order_by(expr: OrderByExpr) -> _DecomposedOrderBy:
    """Decomposes a SQLAlchemy ordering expression into its column, direction and source element.

    Supports bare columns and ``asc()``/``desc()`` optionally wrapped with
    ``nulls_first()``/``nulls_last()``.

    Args:
        expr: A root-model column or unary ordering expression derived from one.

    Returns:
        The decomposed expression.

    Raises:
        StrawchemyFieldError: If the expression uses an unsupported modifier or no
            column can be resolved from it.
    """
    descending = False
    nulls: Literal["first", "last"] | None = None
    element = expr
    while isinstance(element, UnaryExpression):
        modifier = element.modifier
        if modifier is operators.asc_op:
            descending = False
        elif modifier is operators.desc_op:
            descending = True
        elif modifier is operators.nullsfirst_op:
            nulls = "first"
        elif modifier is operators.nullslast_op:
            nulls = "last"
        else:
            msg = f"Unsupported ordering modifier in `default_order_by`: {modifier!r}"
            raise StrawchemyFieldError(msg)
        element = element.element

    if not element.key:
        msg = f"Could not resolve a column from `default_order_by` expression: {expr!r}"
        raise StrawchemyFieldError(msg)
    return _DecomposedOrderBy.from_parts(element.key, descending, nulls, element)


class EnumDTO(DTOBase[Any], Enum):
    __field_definitions__: dict[str, GraphQLFieldDefinition]

    @property
    def field_definition(self) -> GraphQLFieldDefinition:
        return self.__field_definitions__[self.value]


class MappedStrawberryGraphQLDTO(StrawchemyObject, MappedStrawberryDTO[ModelT]): ...


class UnmappedStrawberryGraphQLDTO(StrawchemyObject, StrawberryDTO[ModelT]): ...


class GraphQLFilterDTO(UnmappedStrawberryGraphQLDTO[DeclarativeBase]):
    @property
    def dto_set_fields(self) -> list[str]:
        return [name for name in self.__dto_field_definitions__ if getattr(self, name) is not strawberry.UNSET]


class AggregateDTO(UnmappedStrawberryGraphQLDTO[DeclarativeBase]): ...


class AggregationFunctionFilterDTO(UnmappedStrawberryGraphQLDTO[DeclarativeBase]):
    __dto_function_info__: ClassVar[FilterFunctionInfo]

    arguments: list[_ArgumentValue]
    predicate: EqualityComparison[Any]
    distinct: bool | None = None


class OrderByDTO(GraphQLFilterDTO):
    def tree(self, _node: QueryNodeType | None = None) -> QueryNodeType:
        node = _node or QueryNode.root_node(self.__dto_model__)
        key = DTOKey.from_query_node(node)

        for name in self.dto_set_fields:
            value: OrderByDTO | OrderByEnum = getattr(self, name)
            field = self.__strawchemy_definition__.get_field(key, name)
            if isinstance(field, FunctionFieldDefinition) and not field.has_model_field:
                field.model_field = node.value.model_field
            if isinstance(value, OrderByDTO):
                child, _ = node.upsert_child(field, match_on="value_equality")
                value.tree(child)
            else:
                child = node.insert_child(field)
                child.metadata.data.order_by = value
        return node


class BooleanFilterDTO(GraphQLFilterDTO):
    and_: list[Self] = strawberry.field(default_factory=list, name="_and")
    or_: list[Self] = strawberry.field(default_factory=list, name="_or")
    not_: Self | None = strawberry.field(default=strawberry.UNSET, name="_not")

    def filters_tree(self, _node: QueryNodeType | None = None) -> tuple[QueryNodeType, Filter]:
        node = _node or QueryNode.root_node(self.__dto_model__)
        key = DTOKey.from_query_node(node)
        query = Filter(
            and_=[and_val.filters_tree(node)[1] for and_val in self.and_],
            or_=[or_val.filters_tree(node)[1] for or_val in self.or_],
            not_=self.not_.filters_tree(node)[1] if self.not_ else None,
        )
        for name in self.dto_set_fields:
            value: EqualityComparison[Any] | BooleanFilterDTO | AggregateFilterDTO = getattr(self, name)
            field = self.__strawchemy_definition__.get_field(key, name)
            if isinstance(value, BooleanFilterDTO):
                child, _ = node.upsert_child(field, match_on="value_equality")
                _, sub_query = value.filters_tree(child)
                if sub_query:
                    query.and_.append(sub_query)
            elif isinstance(value, AggregateFilterDTO):
                child = node.insert_child(field)
                query.and_.extend(value.flatten(child))
            else:
                value.field_node = node.insert_child(field)
                query.and_.append(value)
        return node, query


class AggregateFilterDTO(GraphQLFilterDTO):
    def flatten(self, aggregation_node: QueryNodeType) -> list[AggregationFilter]:
        aggregations = []
        for name in self.dto_set_fields:
            function_filter: AggregationFunctionFilterDTO = getattr(self, name)
            function_filter.predicate.field_node = aggregation_node
            aggregation_function = function_filter.__dto_function_info__
            function_node = aggregation_node.insert_child(
                FunctionFieldDefinition(
                    dto_config=self.__dto_config__,
                    model=aggregation_node.value.model,
                    model_field_name=aggregation_function.field_name,
                    type_hint=function_filter.__class__,
                    _function=aggregation_function,
                    _model_field=aggregation_node.value.model_field,
                )
            )
            for arg in function_filter.arguments:
                function_node.insert_child(
                    FunctionArgFieldDefinition.from_field(
                        arg.__field_definitions__[arg.value], function=aggregation_function
                    )
                )
            aggregations.append(
                AggregationFilter(
                    function_info=aggregation_function,
                    field_node=function_node,
                    predicate=function_filter.predicate,
                    distinct=function_filter.distinct,
                )
            )
        return aggregations
