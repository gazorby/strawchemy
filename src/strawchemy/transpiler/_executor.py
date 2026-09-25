"""Runs a planned query and groups its rows into models and computed values."""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeAlias

from sqlalchemy import inspect
from sqlalchemy.exc import MultipleResultsFound
from typing_extensions import Self

from strawchemy.dto import ModelT
from strawchemy.exceptions import QueryResultError
from strawchemy.repository.typing import AnyAsyncSession, AnySyncSession, DeclarativeT

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

    from sqlalchemy import ColumnElement, Label, Result, Select, StatementLambdaElement

    from strawchemy.dto.strawberry import GraphQLFieldDefinition
    from strawchemy.transpiler._plan import QueryPlan
    from strawchemy.typing import QueryNodeType


__all__ = ("AsyncQueryExecutor", "NodeResult", "QueryExecutor", "QueryResult", "SyncQueryExecutor")

RelatedKey: TypeAlias = "tuple[QueryNodeType, tuple[Any, ...] | None]"
"""Identifies one element of a related collection: its relation node and its identity key."""
RelatedObjects: TypeAlias = "Mapping[int, Mapping[int, list[Any]]]"
"""Relation node ``id`` -> its related objects by parent object ``id``; ids avoid hashing nodes, which walks their path."""


@dataclass
class NodeResult(Generic[ModelT]):
    """One model of a query result, with its computed values."""

    model: ModelT
    computed_values: dict[QueryNodeType, Any]
    related_computed_values: Mapping[RelatedKey, dict[QueryNodeType, Any]] = dataclasses.field(default_factory=dict)
    """Computed values of every related object of the query, by relation node and primary key."""
    related_objects: RelatedObjects = dataclasses.field(default_factory=dict)
    """Related objects of every selected relation, by relation node and parent object."""

    def value(self, key: QueryNodeType) -> Any:
        """Returns the value of ``key``: a computed value, selected related objects, or else the model attribute.

        Raises:
            QueryResultError: If ``key`` is a relation the query did not select.
        """
        if key.value.is_computed or key.metadata.data.is_transform:
            return self.computed_values[key]
        if key.value.is_relation:
            if (by_parent := self.related_objects.get(id(key))) is None:
                msg = f"Relation {key.value.name!r} was not selected by the query"
                raise QueryResultError(msg)
            related = by_parent.get(id(self.model), [])
            return related if key.value.uselist else next(iter(related), None)
        return getattr(self.model, key.value.model_field_name)

    def copy_with(self, node: QueryNodeType, model: Any) -> Self:
        """Returns a copy for ``model``, a related object reached through ``node``, with its own computed values."""
        computed_values = self.related_computed_values.get((node, inspect(model).identity), self.computed_values)
        return dataclasses.replace(self, model=model, computed_values=computed_values)


@dataclass
class QueryResult(Generic[ModelT]):
    """Models returned by a query, with their computed values and those of the whole query."""

    nodes: Sequence[ModelT] = dataclasses.field(default_factory=list)
    node_computed_values: Sequence[dict[QueryNodeType, Any]] = dataclasses.field(default_factory=list)
    """Computed values of each model in ``nodes``, in the same order."""
    query_computed_values: defaultdict[QueryNodeType, Any] = dataclasses.field(
        default_factory=lambda: defaultdict(lambda: None)
    )
    """Values computed over the whole query, such as root aggregations."""
    related_computed_values: Mapping[RelatedKey, dict[QueryNodeType, Any]] = dataclasses.field(default_factory=dict)
    """Computed values of every related object of the query, by relation node and primary key."""
    related_objects: RelatedObjects = dataclasses.field(default_factory=dict)
    """Related objects of every selected relation, by relation node and parent object."""

    def __post_init__(self) -> None:
        if not self.node_computed_values:
            self.node_computed_values = [{} for _ in range(len(self.nodes))]

    def __iter__(self) -> Generator[NodeResult[ModelT]]:
        for model, computed_values in zip(self.nodes, self.node_computed_values, strict=False):
            yield NodeResult(model, computed_values, self.related_computed_values, self.related_objects)

    def filter_in(self, **kwargs: Sequence[Any]) -> Self:
        """Returns the results whose attribute named by each keyword is in the given values."""
        filtered = [
            (model, computed_values)
            for model, computed_values in zip(self.nodes, self.node_computed_values, strict=False)
            if all(getattr(model, key) in value for key, value in kwargs.items())
        ]
        nodes, computed_values = list(map(list, zip(*filtered, strict=False))) if filtered else ([], [])
        return dataclasses.replace(self, nodes=nodes, node_computed_values=computed_values)

    def value(self, key: QueryNodeType) -> Any:
        """Returns a value computed over the whole query, or ``None``."""
        return self.query_computed_values[key]

    def one(self) -> NodeResult[ModelT]:
        """Returns the only result.

        Raises:
            QueryResultError: If there is not exactly one result.
        """
        if len(self.nodes) != 1 or len(self.node_computed_values) != 1:
            msg = f"Expected one item, got {len(self.nodes)}"
            raise QueryResultError(msg)
        return NodeResult(
            self.nodes[0], self.node_computed_values[0], self.related_computed_values, self.related_objects
        )

    def one_or_none(self) -> NodeResult[ModelT] | None:
        """Returns the only result, or ``None`` if there is not exactly one."""
        try:
            return self.one()
        except QueryResultError:
            return None


@dataclass
class QueryExecutor(Generic[DeclarativeT]):
    """Runs the statement of a ``QueryPlan`` and turns its rows into a ``QueryResult``."""

    plan: QueryPlan
    id_field_definitions: list[GraphQLFieldDefinition]
    """Primary-key fields of the queried model, used by the repository to fetch by id."""
    execution_options: dict[str, Any] | None = None
    extra_where: list[ColumnElement[bool]] = dataclasses.field(default_factory=list)
    """WHERE predicates added to the planned statement."""

    @property
    def column_map(self) -> Mapping[QueryNodeType, ColumnElement[Any]]:
        """Computed, transform and root aggregation node -> its result column."""
        return self.plan.column_map

    @property
    def identity_columns(self) -> Mapping[QueryNodeType, tuple[ColumnElement[Any], ...]]:
        """Related level owning computed values -> its primary-key columns."""
        return self.plan.identity_columns

    @property
    def root_aggregation_functions(self) -> list[Label[Any]]:
        """Window function columns of the root aggregations."""
        return list(self.plan.root_aggregation_functions)

    def add_where(self, *predicates: ColumnElement[bool]) -> None:
        """Adds WHERE predicates to the planned statement, such as a primary-key lookup."""
        self.extra_where.extend(predicates)

    def _to_query_result(
        self, result: Result[tuple[DeclarativeT, Any]], fetch: Literal["one_or_none", "all"]
    ) -> QueryResult[DeclarativeT]:
        """Groups result rows by root model into a ``QueryResult``.

        A root model spans one row per combination of its related objects, and each row holds the computed values of
        that combination. Those values are stored under the primary key of the related object they belong to.

        Raises:
            MultipleResultsFound: If more than one root model is returned while fetching one.
        """
        nodes: list[DeclarativeT] = []
        computed: list[dict[QueryNodeType, Any]] = []
        related: dict[RelatedKey, dict[QueryNodeType, Any]] = {}
        related_objects: dict[QueryNodeType, dict[int, dict[int, Any]]] = {
            node: {} for node in self.plan.relation_entities
        }
        positions = {node: position for position, node in enumerate(self.plan.relation_entities, start=1)}
        entities = [
            (position, related_objects[node], positions.get(node.parent, 0)) for node, position in positions.items()
        ]
        seen: set[int] = set()
        for row in result.all():
            obj = row[0]
            mapping = row._mapping  # noqa: SLF001  # Row exposes computed values only via _mapping keyed by Label.
            row_computed = {node: mapping[label] for node, label in self.column_map.items() if label in mapping}
            for node, columns in self.identity_columns.items():
                related[node, tuple(mapping[column] for column in columns)] = row_computed
            for position, by_parent, parent_position in entities:
                if (related_object := row[position]) is not None:
                    by_parent.setdefault(id(row[parent_position]), {})[id(related_object)] = related_object
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            nodes.append(obj)
            computed.append(row_computed)

        if fetch == "one_or_none" and len(nodes) > 1:
            msg = "Multiple rows were found when one or none was required"
            raise MultipleResultsFound(msg)

        root_agg_label_set = set(self.root_aggregation_functions)
        root_agg_nodes = {node for node, label in self.column_map.items() if label in root_agg_label_set}
        first_computed = computed[0] if computed else {}
        query_computed_values = {node: first_computed[node] for node in root_agg_nodes if node in first_computed}

        return QueryResult(
            nodes=nodes,
            node_computed_values=computed,
            query_computed_values=defaultdict(lambda: None) | query_computed_values,
            related_computed_values=related,
            related_objects={
                id(node): {identity: list(objects.values()) for identity, objects in by_parent.items()}
                for node, by_parent in related_objects.items()
            },
        )

    def statement(self) -> Select[tuple[DeclarativeT]] | StatementLambdaElement:
        """Returns the planned statement with the extra WHERE predicates and execution options."""
        statement = self.plan.emit()
        if self.extra_where:
            statement = statement.where(*self.extra_where)
        if self.execution_options:
            statement = statement.execution_options(**self.execution_options)
        return statement


@dataclass
class AsyncQueryExecutor(QueryExecutor[DeclarativeT]):
    """Query executor for async sessions."""

    async def execute(self, session: AnyAsyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Runs the statement and returns the raw result."""
        return await session.execute(self.statement())

    async def list(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Runs the statement and returns all results."""
        return self._to_query_result(await self.execute(session), "all")

    async def get_one_or_none(self, session: AnyAsyncSession) -> QueryResult[DeclarativeT]:
        """Runs the statement and returns at most one result."""
        return self._to_query_result(await self.execute(session), "one_or_none")


@dataclass
class SyncQueryExecutor(QueryExecutor[DeclarativeT]):
    """Query executor for sync sessions."""

    def execute(self, session: AnySyncSession) -> Result[tuple[DeclarativeT, Any]]:
        """Runs the statement and returns the raw result."""
        return session.execute(self.statement())

    def list(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Runs the statement and returns all results."""
        return self._to_query_result(self.execute(session), "all")

    def get_one_or_none(self, session: AnySyncSession) -> QueryResult[DeclarativeT]:
        """Runs the statement and returns at most one result."""
        return self._to_query_result(self.execute(session), "one_or_none")
