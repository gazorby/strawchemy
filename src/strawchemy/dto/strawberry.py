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
    EnumDTOT,
    FunctionInfo,
    GraphQLPurpose,
    OrderByDTOT,
    OrderByExpr,
    QueryNodeType,
)
from strawchemy.utils.graph import AnyNode, GraphMetadata, MatchOn, Node, NodeMetadata, NodeT
from strawchemy.utils.text import camel_to_snake

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterator

    from sqlalchemy import ColumnElement
    from strawberry.types.field import StrawberryField

    from strawchemy.schema.filters import EqualityComparison, GraphQLComparison
    from strawchemy.schema.filters.fields import CustomFilterApply, JoinStrategy

T = TypeVar("T")


class _ArgumentValue:
    __field_definitions__: ClassVar[dict[str, DTOFieldDefinition[DeclarativeBase, QueryableAttribute[Any]]]]

    value: str


class RelationFilterDTO(Struct, Generic[OrderByDTOT, EnumDTOT], frozen=True, dict=True):
    limit: int | None = None
    offset: int | None = None
    order_by: tuple[OrderByDTOT, ...] = field(default_factory=tuple)
    distinct_on: tuple[EnumDTOT, ...] = field(default_factory=tuple)

    @cached_property
    def _json(self) -> bytes:
        return json.encode(self)

    def __bool__(self) -> bool:
        return bool(self.limit or self.offset or self.order_by or self.distinct_on)

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
    response_keys: tuple[str, ...] = ()
    """Names under which the node's value appears in the GraphQL response: the field name or its aliases."""

    @property
    def is_transform(self) -> bool:
        return bool(self.json_path)

    @property
    def arguments(self) -> tuple[RelationFilterDTO, str | None]:
        """Field arguments that change the node's value, so that nodes differing by them are not merged."""
        return self.relation_filter, self.json_path


@dataclass(slots=True)
class StrawchemyDefinition:
    description: str = "GraphQL type"
    is_root_aggregation_type: bool = False
    query_hook: QueryHook[Any] | list[QueryHook[Any]] | None = None
    filter: type[Any] | None = None
    order_by: type[Any] | None = None
    distinct_on: type[Any] | None = None
    purpose: GraphQLPurpose | None = None

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
    __dto_field_definitions__: ClassVar[dict[str, GraphQLFieldDefinition]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        existing = cls.__dict__.get("__strawchemy_definition__")
        if existing is None:
            cls.__strawchemy_definition__ = StrawchemyDefinition()
        else:
            cls.__strawchemy_definition__ = copy(existing)


@dataclass
class OutputFunctionInfo:
    function: AggregationFunction
    output_type: Any
    require_arguments: bool = True
    default: Any = DTOMissing


@dataclass
class FilterFunctionInfo:
    function: AggregationFunction
    """SQL aggregate this filter applies."""
    enum_fields: type[EnumDTO]
    """Enum of the columns the function may aggregate, exposed as its ``arguments``."""
    aggregation_type: AggregationType
    """Type filter selecting the candidate columns; several functions can share one."""
    comparison_type: type[GraphQLComparison]
    """Comparison input the ``predicate`` exposes, stored subscripted (``OrderComparison[int]``)."""
    comparison_data_type: type[Any]
    """Scalar the predicate compares against, used to build restricted comparisons."""
    require_arguments: bool = True
    """Whether ``arguments`` is mandatory; ``count`` aggregates rows and needs none."""

    field_name_: str | None = None
    """Generated field name when it differs from ``function`` (e.g. ``min_datetime``)."""

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
    graphql_field: StrawberryField | None = None
    """Prebuilt strawberry field carrying explicit field config."""

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


@dataclass(eq=False, repr=False, kw_only=True)
class CustomFilterFieldDefinition(GraphQLFieldDefinition):
    """Field definition for a custom-apply virtual filter field."""

    apply: CustomFilterApply
    """The custom filter callable; always set for this field type."""
    join: JoinStrategy = "exists"
    """Fold-back strategy used by the transpiler (``"exists"`` or ``"in"``)."""


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
        return tuple((path_node.value, path_node.metadata.data.arguments) for path_node in node.path_from_root())

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
class CustomFilter:
    """A set custom-apply filter value, ready to be folded into the query."""

    apply: CustomFilterApply
    """The custom filter callable (see ``CustomFilterApply``)."""
    value: Any
    """The scalar value supplied in the GraphQL query."""
    join: JoinStrategy
    """Fold-back strategy (``"exists"`` or ``"in"``)."""
    field_node: QueryNodeType
    """The model's query node, used to correlate the EXISTS/IN subquery."""


@dataclass
class NotExistsFilter:
    """A ``_not`` over to-many relations, tested with a correlated NOT EXISTS so that no related row matches."""

    dto_filter: BooleanFilterDTO
    """The negated filter."""
    field_node: QueryNodeType
    """The node of the model ``dto_filter`` applies to, used to correlate the subquery."""


@dataclass
class Filter:
    and_: list[Self | GraphQLComparison | AggregationFilter | CustomFilter | NotExistsFilter] = dataclasses.field(
        default_factory=list
    )
    or_: list[Self] = dataclasses.field(default_factory=list)
    not_: Self | None = None
    relation: QueryNodeType | None = None
    """Relation node the filter tests the related rows of."""

    def __bool__(self) -> bool:
        return bool(self.and_ or self.or_ or self.not_)

    def join_path(self) -> list[QueryNodeType]:
        """Returns the relations in which every row passing the filter must have a related row."""
        nodes = self.relation.path_from_root() if self.relation else []
        for value in self.and_:
            if isinstance(value, Filter):
                nodes.extend(value.join_path())
        if self.or_:
            first, *others = (branch.join_path() for branch in self.or_)
            nodes.extend(node for node in first if all(node in other for other in others))
        return list(dict.fromkeys(nodes))

    def iter_leaves(self) -> Iterator[GraphQLComparison | AggregationFilter | CustomFilter | NotExistsFilter]:
        """Yields every predicate in this filter tree in traversal order.

        Walks the ``and_``, ``or_`` and ``not_`` branches depth-first.
        """
        for value in self.and_:
            if isinstance(value, Filter):
                yield from value.iter_leaves()
            else:
                yield value
        for value in self.or_:
            yield from value.iter_leaves()
        if self.not_ is not None:
            yield from self.not_.iter_leaves()

    def iter_aggregation_filters(self) -> Iterator[AggregationFilter]:
        """Yields every ``AggregationFilter`` in this filter tree in traversal order."""
        return (leaf for leaf in self.iter_leaves() if isinstance(leaf, AggregationFilter))


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
    def has_order(self) -> bool:
        """Whether any field of this input or of its nested inputs is set to a direction."""
        return any(
            not isinstance(value, OrderByDTO) or value.has_order()
            for value in (getattr(self, name) for name in self.dto_set_fields)
        )

    def tree(self, _node: QueryNodeType | None = None) -> QueryNodeType:
        node = _node or QueryNode.root_node(self.__dto_model__)

        for name in self.dto_set_fields:
            value: OrderByDTO | OrderByEnum = getattr(self, name)
            field = self.__dto_field_definitions__[name]
            if isinstance(field, FunctionFieldDefinition) and not field.has_model_field:
                field.model_field = node.value.model_field
            if isinstance(value, OrderByDTO):
                if not value.has_order():
                    continue
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

    @classmethod
    def _from_fields(cls, **fields: object) -> Self:
        return cls(**fields)

    @classmethod
    def all_of(cls, filters: list[Self]) -> Self:
        """Returns a filter matching the rows that every one of ``filters`` matches."""
        return cls._from_fields(and_=filters)

    def conjuncts(self) -> list[Self]:
        """Splits the filter into filters whose AND is equivalent to it, flattening nested ``_and``."""
        parts = [self._from_fields(**{name: getattr(self, name)}) for name in self.dto_set_fields]
        for and_val in self.and_:
            parts.extend(and_val.conjuncts())
        if self.or_:
            parts.append(self._from_fields(or_=self.or_))
        if self.not_:
            parts.append(self._from_fields(not_=self.not_))
        return parts

    def _filtering_fields(
        self,
    ) -> Iterator[tuple[GraphQLFieldDefinition, EqualityComparison[Any] | BooleanFilterDTO | AggregateFilterDTO]]:
        """Yields the set fields holding a predicate, skipping empty comparisons and relation filters."""
        for name in self.dto_set_fields:
            value: EqualityComparison[Any] | BooleanFilterDTO | AggregateFilterDTO = getattr(self, name)
            field = self.__dto_field_definitions__[name]
            if isinstance(field, CustomFilterFieldDefinition):
                yield field, value
            elif isinstance(value, (BooleanFilterDTO, AggregateFilterDTO)):
                if value.has_filter():
                    yield field, value
            elif value.has_operator():
                yield field, value

    def has_filter(self) -> bool:
        """Whether this filter or one of its nested filters holds a predicate."""
        return (
            any(True for _ in self._filtering_fields())
            or any(branch.has_filter() for branch in (*self.and_, *self.or_))
            or bool(self.not_ and self.not_.has_filter())
        )

    def tests_to_many(self) -> bool:
        """Whether the filter tests the rows of a to-many relation outside a nested ``_not``."""
        for definition, value in self._filtering_fields():
            if (
                isinstance(value, BooleanFilterDTO)
                and not isinstance(definition, CustomFilterFieldDefinition)
                and (definition.uselist or value.tests_to_many())
            ):
                return True
        return any(branch.tests_to_many() for branch in (*self.and_, *self.or_))

    def filters_tree(self, _node: QueryNodeType | None = None) -> tuple[QueryNodeType, Filter]:
        node = _node or QueryNode.root_node(self.__dto_model__)
        query = Filter(
            and_=[and_val.filters_tree(node)[1] for and_val in self.and_],
            or_=[or_val.filters_tree(node)[1] for or_val in self.or_ if or_val.has_filter()],
        )
        if self.not_ and self.not_.tests_to_many():
            query.and_.append(NotExistsFilter(dto_filter=self.not_, field_node=node))
        elif self.not_ and self.not_.has_filter():
            query.not_ = self.not_.filters_tree(node)[1]
        for definition, value in self._filtering_fields():
            if isinstance(definition, CustomFilterFieldDefinition):
                query.and_.append(
                    CustomFilter(apply=definition.apply, value=value, join=definition.join, field_node=node)
                )
            elif isinstance(value, BooleanFilterDTO):
                child, _ = node.upsert_child(definition, match_on="value_equality")
                _, sub_query = value.filters_tree(child)
                sub_query.relation = child
                query.and_.append(sub_query)
            elif isinstance(value, AggregateFilterDTO):
                child = node.insert_child(definition)
                query.and_.extend(value.flatten(child))
            else:
                value.field_node = node.insert_child(definition)
                query.and_.append(value)
        return node, query


class AggregateFilterDTO(GraphQLFilterDTO):
    def _function_filters(self) -> Iterator[AggregationFunctionFilterDTO]:
        for name in self.dto_set_fields:
            function_filter: AggregationFunctionFilterDTO = getattr(self, name)
            if function_filter.predicate.has_operator():
                yield function_filter

    def has_filter(self) -> bool:
        """Whether an aggregation function of this filter has a predicate."""
        return any(True for _ in self._function_filters())

    def flatten(self, aggregation_node: QueryNodeType) -> list[AggregationFilter]:
        aggregations = []
        for function_filter in self._function_filters():
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
