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
import sys
from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    Self,
    TypeVar,
    overload,
    override,
)

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from strawchemy.dto.backend.dataclass import DataclassDTO, MappedDataclassDTO
from strawchemy.dto.backend.pydantic import MappedPydanticDTO, PydanticDTO
from strawchemy.dto.base import DTOBase, DTOFieldDefinition, ModelFieldT, ModelT
from strawchemy.dto.types import DTO_MISSING, DTOConfig, DTOFieldConfig, Purpose
from strawchemy.graph import GraphError, MatchOn, Node, UndefinedType, undefined
from strawchemy.utils import camel_to_snake

from .constants import LIMIT_KEY, OFFSET_KEY, ORDER_BY_KEY
from .filters import AnyOrderComparison
from .typing import OrderByDTOT

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Sequence

    from strawchemy.sqlalchemy.hook import QueryHook

    from .filters import GenericComparison, GraphQLComparison, OrderComparison
    from .typing import AggregationFunction, AggregationType, FunctionInfo

T = TypeVar("T")


def _ensure_list(value: Any) -> Any:
    return value if isinstance(value, list) else [value]


class _HasValue(Protocol, Generic[ModelT, ModelFieldT]):
    __field_definitions__: dict[str, DTOFieldDefinition[ModelT, ModelFieldT]]

    value: str


@dataclass
class QueryMetadata:
    root_aggregations: bool = False


class StrawchemyDTOAttributes:
    __strawchemy_description__: ClassVar[str] = "GraphQL type"
    __strawchemy_is_root_aggregation_type__: ClassVar[bool] = False
    __strawchemy_field_map__: ClassVar[dict[DTOKey, GraphQLFieldDefinition[Any, Any]]] = {}
    __strawchemy_query_hook__: QueryHook[Any] | Sequence[QueryHook[Any]] | None = None
    __strawchemy_filter__: type[Any] | None = None
    __strawchemy_order_by__: type[Any] | None = None
    __strawchemy_validation_cls__: type[MappedPydanticDTO[Any]] | None = None


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

    separator: str = ":"

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
    def from_dto_node(cls, node: Node[Any, None]) -> Self:
        return cls([node.value.model])

    @classmethod
    def from_query_node(cls, node: QueryNode[ModelT, ModelFieldT]) -> Self:
        if node.is_root:
            return cls([node.value.model])
        if node.value.related_model:
            return cls([node.value.related_model])
        return cls([node.value.model])


class RelationFilterDTO(BaseModel, Generic[OrderByDTOT]):
    limit: int | None = Field(default=None, alias=LIMIT_KEY)
    offset: int | None = Field(default=None, alias=OFFSET_KEY)
    order_by: Annotated[list[OrderByDTOT], BeforeValidator(_ensure_list)] | None = Field(
        default=None, alias=ORDER_BY_KEY
    )

    @override
    def __hash__(self) -> int:
        return hash(self.model_dump_json())


@dataclass
class OutputFunctionInfo:
    function: AggregationFunction
    output_type: Any
    require_arguments: bool = True
    default: Any = DTO_MISSING


@dataclass
class FilterFunctionInfo(Generic[ModelT, ModelFieldT, AnyOrderComparison]):
    function: AggregationFunction
    enum_fields: type[EnumDTO]
    aggregation_type: AggregationType
    comparison_type: type[GraphQLComparison[ModelT, ModelFieldT]]
    require_arguments: bool = True

    field_name_: str | None = None

    @property
    def field_name(self) -> str:
        if self.field_name_ is None:
            return self.function
        return self.field_name_


@dataclass(kw_only=True, eq=False, repr=False)
class GraphQLFieldDefinition(DTOFieldDefinition[ModelT, ModelFieldT], Generic[ModelT, ModelFieldT]):
    config: DTOFieldConfig = dataclasses.field(default_factory=DTOFieldConfig)
    is_aggregate: bool = False
    is_function: bool = False
    is_function_arg: bool = False

    _function: FunctionInfo[ModelT, ModelFieldT] | None = None

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
    def function(self, strict: Literal[False]) -> FunctionInfo[ModelT, ModelFieldT] | None: ...

    @overload
    def function(self, strict: Literal[True]) -> FunctionInfo[ModelT, ModelFieldT]: ...

    @overload
    def function(self, strict: bool = False) -> FunctionInfo[ModelT, ModelFieldT] | None: ...

    def function(self, strict: bool = False) -> FunctionInfo[ModelT, ModelFieldT] | None:
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


@dataclass(kw_only=True, eq=False, repr=False)
class AggregateFieldDefinition(GraphQLFieldDefinition[ModelT, ModelFieldT]):
    is_relation: bool = True
    is_aggregate: bool = True


@dataclass(kw_only=True, eq=False, repr=False)
class FunctionFieldDefinition(GraphQLFieldDefinition[ModelT, ModelFieldT]):
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
        function: FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]] | OutputFunctionInfo,
        **kwargs: Any,
    ) -> Self:
        return super().from_field(field_def, _function=function, **kwargs)

    @override
    def _hash_identity(self) -> Hashable:
        return (
            super()._hash_identity(),
            self.function(strict=True).function,
            self.function(strict=True).require_arguments,
        )


@dataclass(kw_only=True, eq=False, repr=False)
class FunctionArgFieldDefinition(FunctionFieldDefinition[ModelT, ModelFieldT]):
    def __post_init__(self) -> None:
        super().__post_init__()
        self.is_function_arg = True


@dataclass(eq=False)
class QueryNode(Node[GraphQLFieldDefinition[ModelT, ModelFieldT], None], Generic[ModelT, ModelFieldT]):
    children: list[Self] = dataclasses.field(default_factory=list)
    relation_filter: RelationFilterDTO[Any] = dataclasses.field(default_factory=RelationFilterDTO)
    query_metadata: QueryMetadata = dataclasses.field(default_factory=QueryMetadata)

    @classmethod
    def _node_hash_identity(cls, node: Self) -> Hashable:
        return (*[parent.value for parent in node.path_from_root()], node.relation_filter)

    def _hash_identity(self) -> Hashable:
        return (self._node_hash_identity(self.root), self._node_hash_identity(self))

    def _hash(self) -> int:
        # Ensure positive
        return hash(self._hash_identity()) % 2**sys.hash_info.width

    def _update_new_child(self, child: Self) -> Self:
        if self.value.is_function:
            child.value = FunctionArgFieldDefinition.from_field(child.value, function=self.value.function(strict=True))
        child.query_metadata = self.query_metadata
        return child

    def first_aggregate_parent(self) -> Self:
        return next(parent for parent in self.iter_parents() if parent.value.is_aggregate)

    @override
    def _new(
        self,
        value: GraphQLFieldDefinition[ModelT, ModelFieldT],
        metadata: None | UndefinedType = undefined,
        parent: Self | None = None,
    ) -> Self:
        new = super()._new(value, metadata, parent)
        new.query_metadata = self.query_metadata
        return new

    @override
    def insert_node(self, child: Self) -> Self:
        return self._update_new_child(super().insert_node(child))

    @override
    def insert_child(
        self, value: GraphQLFieldDefinition[ModelT, ModelFieldT], metadata: None | UndefinedType = undefined
    ) -> Self:
        return self._update_new_child(super().insert_child(value, metadata))

    @override
    @classmethod
    def match_nodes(
        cls,
        left: Self,
        right: Self,
        match_on: Callable[[Self, Self], bool] | MatchOn,
    ) -> bool:
        if match_on == "value_equality":
            return left.value.model is right.value.model and left.value.model_field_name == right.value.model_field_name
        return super(cls, cls).match_nodes(left, right, match_on)

    @classmethod
    def root_node(cls, model: type[ModelT], root_aggregations: bool = False, **kwargs: Any) -> Self:
        root_name = camel_to_snake(model.__name__)
        field_def = GraphQLFieldDefinition(
            config=DTOFieldConfig(),
            dto_config=DTOConfig(Purpose.READ),
            model=model,
            model_field_name=root_name,
            is_relation=False,
            type_hint=model,
        )
        return cls(value=field_def, query_metadata=QueryMetadata(root_aggregations=root_aggregations), **kwargs)

    @overload
    def non_computed_parent(self, strict: Literal[True]) -> Self: ...

    @overload
    def non_computed_parent(self, strict: Literal[False]) -> Self | None: ...

    @overload
    def non_computed_parent(self, strict: bool) -> Self | None: ...

    def non_computed_parent(self, strict: bool = False) -> Self | None:
        parent = self.parent
        if not parent:
            if strict:
                msg = "No non computed parent found"
                raise GraphError(msg)
            return None
        if parent.value.is_computed:
            return parent.non_computed_parent(strict)
        return parent

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.value.model_field_name}>"

    @override
    def __hash__(self) -> int:
        return self._hash()

    @override
    def __eq__(self, other: object) -> bool:
        return hash(self) == hash(other)

    @override
    def __ne__(self, other: object) -> bool:
        return hash(self) != hash(other)


@dataclass(eq=False, repr=False)
class OrderByNode(QueryNode[ModelT, ModelFieldT]):
    order_by: OrderByEnum | None = None

    def __gt__(self, other: Self) -> bool:
        return self.insert_order > other.insert_order

    def __lt__(self, other: Self) -> bool:
        return self.insert_order < other.insert_order

    def __le__(self, other: Self) -> bool:
        return self.insert_order <= other.insert_order

    def __ge__(self, other: Self) -> bool:
        return self.insert_order >= other.insert_order


@dataclass
class AggregationFilter(Generic[ModelT, ModelFieldT]):
    function_info: FilterFunctionInfo[ModelT, ModelFieldT, OrderComparison[Any, Any, Any]]
    predicate: GenericComparison[Any, ModelT, ModelFieldT]
    field_node: QueryNode[ModelT, ModelFieldT]
    distinct: bool | None = None


@dataclass
class Filter(Generic[ModelT, ModelFieldT]):
    and_: list[Self | GraphQLComparison[ModelT, ModelFieldT] | AggregationFilter[ModelT, ModelFieldT]] = (
        dataclasses.field(default_factory=list)
    )
    or_: list[Self] = dataclasses.field(default_factory=list)
    not_: Self | None = None

    def __bool__(self) -> bool:
        return bool(self.and_ or self.or_ or self.not_)


class OrderByEnum(Enum):
    ASC = "ASC"
    ASC_NULLS_FIRST = "ASC_NULLS_FIRST"
    ASC_NULLS_LAST = "ASC_NULLS_LAST"
    DESC = "DESC"
    DESC_NULLS_FIRST = "DESC_NULLS_FIRST"
    DESC_NULLS_LAST = "DESC_NULLS_LAST"


class EnumDTO(DTOBase[Any], Enum):
    __field_definitions__: dict[str, GraphQLFieldDefinition[Any, Any]]

    @property
    def field_definition(self) -> GraphQLFieldDefinition[Any, Any]: ...


class MappedDataclassGraphQLDTO(StrawchemyDTOAttributes, MappedDataclassDTO[ModelT]): ...


class UnmappedDataclassGraphQLDTO(StrawchemyDTOAttributes, DataclassDTO[ModelT]): ...


class UnmappedPydanticGraphQLDTO(StrawchemyDTOAttributes, PydanticDTO[ModelT]):
    @property
    def dto_set_fields(self) -> set[str]:
        return {name for name in self.model_fields_set if getattr(self, name) is not None}


class MappedPydanticGraphQLDTO(StrawchemyDTOAttributes, MappedPydanticDTO[ModelT]):
    __strawchemy_filter__: type[Any] | None = None
    __strawchemy_order_by__: type[Any] | None = None


class GraphQLFilterDTO(UnmappedPydanticGraphQLDTO[ModelT]): ...


class AggregateDTO(UnmappedDataclassGraphQLDTO[ModelT]): ...


class AggregationFunctionFilterDTO(UnmappedPydanticGraphQLDTO[ModelT]):
    __dto_function_info__: ClassVar[FilterFunctionInfo[Any, Any, OrderComparison[Any, Any, Any]]]

    arguments: list[_HasValue[ModelT, Any]]
    predicate: GenericComparison[Any, ModelT, Any]
    distinct: bool | None = None


class OrderByDTO(GraphQLFilterDTO[ModelT], Generic[ModelT, ModelFieldT]):
    def tree(self, _node: OrderByNode[Any, ModelFieldT] | None = None) -> OrderByNode[Any, ModelFieldT]:
        node = _node or OrderByNode.root_node(self.__dto_model__)
        key = DTOKey.from_query_node(node)

        for name in self.dto_set_fields:
            value: OrderByDTO[ModelT, ModelFieldT] | OrderByEnum = getattr(self, name)
            field = self.__strawchemy_field_map__[key + name]
            if isinstance(field, FunctionFieldDefinition) and not field.has_model_field:
                field.model_field = node.value.model_field
            if isinstance(value, OrderByDTO):
                child, _ = node.upsert_child(field, match_on="value_equality")
                value.tree(child)
            else:
                child = node.insert_child(field)
                child.order_by = value
        return node


class BooleanFilterDTO(GraphQLFilterDTO[ModelT], Generic[ModelT, ModelFieldT]):
    model_config = ConfigDict(populate_by_name=True)

    and_: list[Self] = Field(default_factory=list, alias="_and")
    or_: list[Self] = Field(default_factory=list, alias="_or")
    not_: Self | None = Field(default=None, alias="_not")

    def filters_tree(
        self, _node: QueryNode[Any, ModelFieldT] | None = None
    ) -> tuple[QueryNode[ModelT, ModelFieldT], Filter[ModelT, ModelFieldT]]:
        node = _node or QueryNode.root_node(self.__dto_model__)
        key = DTOKey.from_query_node(node)
        query = Filter(
            and_=[and_val.filters_tree(node)[1] for and_val in self.and_],
            or_=[or_val.filters_tree(node)[1] for or_val in self.or_],
            not_=self.not_.filters_tree(node)[1] if self.not_ else None,
        )

        for name in self.dto_set_fields - {"and_", "or_", "not_"}:
            value: (
                GenericComparison[Any, ModelT, ModelFieldT]
                | BooleanFilterDTO[ModelT, ModelFieldT]
                | AggregateFilterDTO[ModelT]
            )
            value = getattr(self, name)
            field = self.__strawchemy_field_map__[key + name]
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


class AggregateFilterDTO(GraphQLFilterDTO[ModelT]):
    def flatten(self, aggregation_node: QueryNode[ModelT, ModelFieldT]) -> list[AggregationFilter[ModelT, Any]]:
        aggregations = []
        for name in self.dto_set_fields:
            function_filter: AggregationFunctionFilterDTO[ModelT] = getattr(self, name)
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
